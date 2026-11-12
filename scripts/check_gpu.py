import torch
print("torch", torch.__version__, "cuda build", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print("device:", p.name)
    print("total VRAM: %.2f GiB" % (p.total_memory / 2**30))
    print("bf16 supported:", torch.cuda.is_bf16_supported())
