"""Merge a LoRA adapter into its base model and save the result as a plain HF model (no peft needed to load it).

    python scripts/merge_lora.py --adapter outputs/lora_v2 --out C:/Users/NAD/models/cleanops-assistant-merged

The merge is done in float32 on the CPU and the result is stored as bfloat16 (the dtype the evaluation uses).
The output directory must be OUTSIDE the git repositories (weights are never committed).
"""
import argparse
import pathlib
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3-1.7B")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out).resolve()
    if (pathlib.Path(__file__).resolve().parents[1]) in out.parents:
        raise SystemExit("refusing to write weights inside the repository")
    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.float32)
    model = PeftModel.from_pretrained(model, a.adapter)
    model = model.merge_and_unload()
    model = model.to(torch.bfloat16)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    print("saved", out)


if __name__ == "__main__":
    main()
