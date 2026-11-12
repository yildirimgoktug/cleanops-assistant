"""LoRA fine-tuning of Qwen3-1.7B on the generated conversations (TRL SFTTrainer).

Config (adapted to a 6 GB laptop GPU): bf16 base model, LoRA r=16 alpha=32
dropout 0.05 on q/k/v/o/gate/up/down projections, batch size 1, gradient
accumulation 8, gradient checkpointing, lr 2e-4 linear with ~5% warmup, loss
on assistant tokens only, fixed seed, adapter-only save.

Two deliberate deviations, both measured:
* max length 3456 instead of 1024. The 16 tool definitions in Qwen3's native
  `tools=` format cost ~2,240 tokens on their own, so no example fits in 1024.
* The loss is computed only at assistant positions: the model is called with
  `logits_to_keep=<positions of trained tokens>`, so the 151k-wide logits are
  never materialised for the ~96% of tokens that are masked anyway. This is
  what makes 3k-token sequences fit in 6 GB (the full-logits path needs
  ~1.5 GB per 1k tokens). The loss value is identical to masked cross-entropy.

Assistant-only loss: TRL 0.24's `assistant_only_loss=True` needs `{% generation %}`
markers in the chat template, which Qwen3's stock template does not have. The
data is therefore pre-tokenised with our own renderer (assistant/agent.py,
the same code the agent uses at inference) into `input_ids` + `completion_mask`,
and `completion_only_loss=True` makes TRL's collator mask everything else.

Time box: `--time-budget-min` (default 90). The run starts with an estimated
total; after `--probe-steps` (50) optimizer steps it measures seconds/step and
fixes the final number of steps so the whole run (including periodic evals and
saving) ends within the budget; the linear LR schedule is re-targeted to that
total at that point. `--max-steps N` instead fixes the number of steps up front.

  python train/train_lora.py --time-budget-min 90
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_CACHE", str(ROOT / "outputs" / "hf_datasets_cache"))
sys.path.insert(0, str(ROOT))

T_SCRIPT = time.time()

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from datasets import Dataset  # noqa: E402
from peft import LoraConfig  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback, set_seed  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

from assistant.agent import Renderer  # noqa: E402

MODEL = "Qwen/Qwen3-1.7B"


def load(path, renderer, max_len, limit=None):
    rows, dropped = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            x = json.loads(line)
            ids, mask = renderer.encode_conversation(x["messages"])
            if len(ids) > max_len:
                dropped += 1
                continue
            rows.append({"input_ids": ids, "completion_mask": mask})
            if limit and len(rows) >= limit:
                break
    return Dataset.from_list(rows), dropped


class AssistantLossSFTTrainer(SFTTrainer):
    """SFTTrainer whose loss only materialises logits at trained (assistant) positions."""

    sched_state = {"total": 100, "warmup": 5}

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs["labels"]
        assert labels.shape[0] == 1, "this loss assumes batch size 1"
        shift = labels[0, 1:]
        pos = (shift != -100).nonzero(as_tuple=True)[0]
        # batch size 1 and no padding: no attention_mask, so SDPA can use its memory-efficient causal kernel
        # (an explicit all-ones mask makes it fall back to a kernel that materialises the attention matrix)
        out = model(input_ids=inputs["input_ids"], logits_to_keep=pos, use_cache=False)
        logits = out.logits[0].float()
        loss = F.cross_entropy(logits, shift[pos])
        with torch.no_grad():
            acc = (logits.argmax(-1) == shift[pos]).float().mean().item()
        mode = "train" if model.training else "eval"
        self._metrics[mode]["mean_token_accuracy"].append(acc)
        if os.environ.get("DEBUG_MEM"):
            print(f"[mem] len={labels.shape[1]} trained={len(pos)} alloc={torch.cuda.memory_allocated() / 2**30:.2f} "
                  f"peak={torch.cuda.max_memory_allocated() / 2**30:.2f} t={time.time() - T_SCRIPT:.1f} "
                  f"gc={getattr(model, 'is_gradient_checkpointing', None)} training={model.training}", flush=True)
        return (loss, out) if return_outputs else loss

    def create_scheduler(self, num_training_steps, optimizer=None):
        st = self.sched_state

        def lr_lambda(step):
            if step < st["warmup"]:
                return (step + 1) / st["warmup"]
            return max(0.0, (st["total"] - step) / max(1, st["total"] - st["warmup"]))

        if self.lr_scheduler is None:
            self.lr_scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer or self.optimizer, lr_lambda)
            self._created_lr_scheduler = True
        return self.lr_scheduler


class TimeBox(TrainerCallback):
    """Wall-clock budget across interruptions. State (budget used up to the last checkpoint, the decided
    number of steps, the measured speed) is kept in <out>/timebox_state.json and reloaded on resume.
    Work done after the last checkpoint of an interrupted segment is lost and not counted."""

    def __init__(self, a, trainer_ref, log_path, n_train, prev=None):
        self.a = a
        self.tr = trainer_ref
        self.log = open(log_path, "a", encoding="utf-8")
        self.n_train = n_train
        self.t_train0 = None
        self.start_step = 0
        prev = prev or {}
        self.used_before = prev.get("used_s", 0.0)
        self.segments = prev.get("segments", 0) + 1
        self.decided = a.max_steps or prev.get("decided")
        self.s_per_step = prev.get("s_per_step")
        self.state_path = pathlib.Path(a.out) / "timebox_state.json"

    def used(self):
        return self.used_before + (time.time() - T_SCRIPT)

    def on_train_begin(self, args, state, control, **kw):
        self.t_train0 = time.time()
        self.start_step = state.global_step
        torch.cuda.reset_peak_memory_stats()

    def on_save(self, args, state, control, **kw):
        self.state_path.write_text(json.dumps({"used_s": round(self.used(), 1), "decided": self.decided,
                                               "s_per_step": self.s_per_step, "step": state.global_step,
                                               "segments": self.segments}))
        self.write({"event": "checkpoint", "step": state.global_step, "budget_used_s": round(self.used())})

    def on_step_end(self, args, state, control, **kw):
        measured = state.global_step - self.start_step
        if self.decided is None and state.global_step >= self.a.probe_steps and measured >= 10:
            self.s_per_step = (time.time() - self.t_train0) / measured
            used = self.used()
            n_evals_left_guess = 0
            est_eval = self.a.val_n * (self.s_per_step / self.a.ga) * 0.4
            budget = self.a.time_budget_min * 60 - used - 120  # 2 min margin for final eval + save
            # steps s.t. remaining training + evals fit in the budget
            est_ckpt = 15  # seconds per checkpoint save (adapter + optimizer state)
            now_step = state.global_step
            extra = 0
            while True:
                total = now_step + extra + 1
                n_evals_left_guess = total // self.a.eval_steps - now_step // self.a.eval_steps + 1
                n_ckpt = total // self.a.save_steps - now_step // self.a.save_steps
                if (extra + 1) * self.s_per_step + n_evals_left_guess * est_eval + n_ckpt * est_ckpt > budget:
                    break
                extra += 1
            self.decided = now_step + extra
            AssistantLossSFTTrainer.sched_state["total"] = self.decided
            self.write({"event": "time_box_decision", "step": state.global_step, "s_per_step": round(self.s_per_step, 2),
                        "budget_used_s": round(used), "decided_total_steps": self.decided,
                        "examples_seen_at_end": self.decided * self.a.ga,
                        "epochs_at_end": round(self.decided * self.a.ga / self.n_train, 3)})
        if self.decided is not None and state.global_step >= self.decided:
            control.should_training_stop = True
        if not self.a.max_steps and self.used() > self.a.time_budget_min * 60 - 120:
            self.write({"event": "budget_exhausted", "step": state.global_step, "budget_used_s": round(self.used())})
            control.should_training_stop = True
        return control

    def on_evaluate(self, args, state, control, metrics=None, **kw):
        self.write({"event": "eval", "step": state.global_step, **(metrics or {})})

    def on_log(self, args, state, control, logs=None, **kw):
        logs = dict(logs or {})
        logs.update({"event": "log", "step": state.global_step, "elapsed_s": round(time.time() - T_SCRIPT),
                     "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)})
        self.write(logs)

    def write(self, obj):
        self.log.write(json.dumps(obj) + "\n")
        self.log.flush()
        print(json.dumps(obj), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "generated"))
    ap.add_argument("--out", default=str(ROOT / "outputs" / "lora_v1"))
    ap.add_argument("--max-len", type=int, default=3456)
    ap.add_argument("--max-steps", type=int, default=0, help="fixed number of optimizer steps (disables the time box)")
    ap.add_argument("--epochs", type=float, default=0, help="alternative to --max-steps")
    ap.add_argument("--time-budget-min", type=float, default=90)
    ap.add_argument("--probe-steps", type=int, default=50)
    ap.add_argument("--initial-steps-estimate", type=int, default=160)
    ap.add_argument("--eval-steps", type=int, default=50)
    ap.add_argument("--val-n", type=int, default=64, help="fixed validation subset used for periodic eval")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--ga", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--log", default=str(ROOT / "logs" / "train_log.jsonl"))
    ap.add_argument("--save-steps", type=int, default=8,
                    help="checkpoint (adapter + optimizer) every N optimizer steps; the run resumes from the latest one")
    a = ap.parse_args()
    set_seed(a.seed)
    pathlib.Path(a.log).parent.mkdir(exist_ok=True, parents=True)

    tok = AutoTokenizer.from_pretrained(MODEL)
    renderer = Renderer(tok)
    train_ds, dropped_train = load(pathlib.Path(a.data_dir) / "train.jsonl", renderer, a.max_len)
    val_ds, dropped_val = load(pathlib.Path(a.data_dir) / "val.jsonl", renderer, a.max_len, limit=a.val_n)
    train_ds = train_ds.shuffle(seed=a.seed)
    n_train = len(train_ds)
    if a.epochs:
        a.max_steps = int(a.epochs * n_train / a.ga)
    print(f"train {n_train} (dropped {dropped_train} > {a.max_len}), val subset {len(val_ds)}", flush=True)

    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda")
    model.config.use_cache = False
    peft_config = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    total0 = a.max_steps or a.initial_steps_estimate
    AssistantLossSFTTrainer.sched_state.update(total=total0, warmup=max(1, round(0.05 * total0)))
    # resume after an interruption: latest checkpoint + saved time-box state
    ckpts = sorted(pathlib.Path(a.out).glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
    resume = str(ckpts[-1]) if ckpts else None
    prev = {}
    sp = pathlib.Path(a.out) / "timebox_state.json"
    if resume and sp.exists():
        prev = json.loads(sp.read_text())
        if prev.get("decided"):
            AssistantLossSFTTrainer.sched_state["total"] = prev["decided"]
    cfg = SFTConfig(
        output_dir=a.out, per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=a.ga, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False}, learning_rate=a.lr, lr_scheduler_type="linear",
        warmup_ratio=0.05, bf16=True, logging_steps=5, eval_strategy="steps", eval_steps=a.eval_steps,
        save_strategy="steps", save_steps=a.save_steps, save_total_limit=1, seed=a.seed, data_seed=a.seed, max_length=a.max_len, completion_only_loss=True,
        report_to="none", max_steps=a.max_steps or 100000, dataloader_num_workers=0, prediction_loss_only=True,
        packing=False, dataset_num_proc=None, max_grad_norm=1.0, disable_tqdm=True,
    )
    trainer = AssistantLossSFTTrainer(model=model, args=cfg, train_dataset=train_ds, eval_dataset=val_ds,
                                      processing_class=tok, peft_config=peft_config)
    trainer.model_accepts_loss_kwargs = False  # our loss is a per-sequence mean; Trainer divides by GA
    trainer.model.print_trainable_parameters()
    tb = TimeBox(a, trainer, a.log, n_train, prev)
    trainer.add_callback(tb)
    tb.write({"event": "start", "n_train": n_train, "n_val_subset": len(val_ds), "dropped_train_over_max_len": dropped_train,
              "max_len": a.max_len, "ga": a.ga, "lr": a.lr, "seed": a.seed, "initial_total_steps": total0,
              "time_budget_min": a.time_budget_min, "max_steps_fixed": a.max_steps or None,
              "resume_from": resume and os.path.relpath(resume, ROOT), "segment": tb.segments,
              "budget_used_before_s": round(tb.used_before)})
    trainer.train(resume_from_checkpoint=resume)
    final_eval = trainer.evaluate()
    trainer.model.save_pretrained(a.out)  # adapter only
    tok.save_pretrained(a.out)
    import shutil
    for c in pathlib.Path(a.out).glob("checkpoint-*"):  # keep only the final adapter (disk space)
        shutil.rmtree(c, ignore_errors=True)
    hist = [h for h in trainer.state.log_history if "loss" in h]
    summary = {
        "model": MODEL, "adapter_dir": os.path.relpath(a.out, ROOT),
        "lora": {"r": 16, "alpha": 32, "dropout": 0.05, "target_modules": peft_config.target_modules and sorted(peft_config.target_modules)},
        "optimizer_steps": trainer.state.global_step, "grad_accum": a.ga, "batch_size": 1,
        "examples_seen": trainer.state.global_step * a.ga, "train_examples_available": n_train,
        "epochs": round(trainer.state.global_step * a.ga / n_train, 3),
        "lr": a.lr, "schedule": "linear with warmup, re-targeted by the time box" if not a.max_steps else "linear with warmup",
        "warmup_steps": AssistantLossSFTTrainer.sched_state["warmup"], "scheduled_total_steps": AssistantLossSFTTrainer.sched_state["total"],
        "max_len": a.max_len, "seed": a.seed, "time_budget_min": a.time_budget_min,
        "s_per_step_probe": round(tb.s_per_step, 2) if tb.s_per_step else None,
        "wall_clock_s": round(tb.used()), "segments": tb.segments,
        "wall_clock_note": "budget used across segments, counted up to each segment's last checkpoint for interrupted segments",
        "last_segment_wall_s": round(time.time() - T_SCRIPT), "train_runtime_s": round(time.time() - tb.t_train0),
        "first_train_loss": hist[0]["loss"] if hist else None, "final_train_loss": hist[-1]["loss"] if hist else None,
        "final_val_loss": final_eval.get("eval_loss"), "val_subset_n": len(val_ds),
        "eval_history": [{"step": h["step"], "eval_loss": h["eval_loss"]} for h in trainer.state.log_history if "eval_loss" in h],
        "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2 ** 30, 2), "peak_vram_note": "last segment",
        "versions": {"torch": torch.__version__, "transformers": __import__("transformers").__version__,
                     "trl": __import__("trl").__version__, "peft": __import__("peft").__version__},
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "train_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    tb.write({"event": "done", **summary})


if __name__ == "__main__":
    main()
