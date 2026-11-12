import os, time
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL = "Qwen/Qwen3-1.7B"
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda")
msgs = [{"role": "user", "content": "In one sentence, what is a hydraulic press used for?"}]
text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
inputs = tok(text, return_tensors="pt").to("cuda")
torch.cuda.reset_peak_memory_stats()
model.generate(**inputs, max_new_tokens=8, do_sample=False)  # warmup
torch.cuda.synchronize(); t = time.time()
out = model.generate(**inputs, max_new_tokens=64, min_new_tokens=64, do_sample=False)
torch.cuda.synchronize(); dt = time.time() - t
n = out.shape[1] - inputs["input_ids"].shape[1]
print(tok.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True))
print("new tokens: %d, %.2f tok/s" % (n, n / dt))
print("peak VRAM: %.2f GiB" % (torch.cuda.max_memory_allocated() / 2**30))
