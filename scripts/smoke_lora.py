import os, sys, time, shutil, tempfile, argparse
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

ap = argparse.ArgumentParser()
ap.add_argument("--max-len", type=int, default=512)
ap.add_argument("--steps", type=int, default=20)
ap.add_argument("--attn-only", action="store_true")
ap.add_argument("--4bit", dest="four", action="store_true")
a = ap.parse_args()

MODEL = "Qwen/Qwen3-1.7B"
tok = AutoTokenizer.from_pretrained(MODEL)
kw = {}
if a.four:
    from transformers import BitsAndBytesConfig
    kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    kw["device_map"] = {"": 0}
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, **kw)
if not a.four:
    model.to("cuda")
model.config.use_cache = False
if a.four:
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
else:
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
targets = ["q_proj","k_proj","v_proj","o_proj"] + ([] if a.attn_only else ["gate_proj","up_proj","down_proj"])
model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=targets, task_type="CAUSAL_LM"))
model.print_trainable_parameters()

# dummy chat data, padded long enough to actually hit max_len (worst case memory)
filler = " ".join(["Check the filter, log the reading, and report any anomaly to the supervisor."] * 120)
data = []
for i in range(8):
    msgs = [{"role": "user", "content": f"Task {i}: summarise this cleaning log. {filler}"},
            {"role": "assistant", "content": f"Summary {i}: routine checks were logged. {filler}"}]
    txt = tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
    data.append(tok(txt, truncation=True, max_length=a.max_len, return_tensors="pt")["input_ids"][0])
print("seq lens:", [len(d) for d in data][:3], "...")

params = [p for p in model.parameters() if p.requires_grad]
opt = torch.optim.AdamW(params, lr=2e-4)
model.train()
GA = 4
torch.cuda.reset_peak_memory_stats()
losses, step_times = [], []
for step in range(a.steps):
    torch.cuda.synchronize(); t = time.time(); tot = 0.0
    for m in range(GA):
        ids = data[(step * GA + m) % len(data)].unsqueeze(0).to("cuda")
        loss = model(input_ids=ids, labels=ids).loss / GA
        loss.backward(); tot += loss.item()
    opt.step(); opt.zero_grad(set_to_none=True)
    torch.cuda.synchronize(); step_times.append(time.time() - t); losses.append(tot)
    print(f"step {step+1:2d} loss {tot:.4f} {step_times[-1]:.2f}s", flush=True)
tmp = tempfile.mkdtemp(prefix="lora_smoke_")
model.save_pretrained(tmp); shutil.rmtree(tmp)
mode = f"len={a.max_len} attn_only={a.attn_only} 4bit={a.four}"
print(f"RESULT [{mode}] loss {losses[0]:.4f} -> {losses[-1]:.4f}; mean s/step (excl. first) {sum(step_times[1:])/len(step_times[1:]):.2f}; peak VRAM {torch.cuda.max_memory_allocated()/2**30:.2f} GiB")
