# Merged HF model -> GGUF (q8_0 written by the convert script itself) -> optional smaller quantisations.
# Software (all official, pinned):
#   llama.cpp tag v1.0.0 (commit b1b770d90d94cad9e9ea5b993bdbc383a522fb28), checked out outside the repo:
#     git clone --depth 1 --branch v1.0.0 https://github.com/ggml-org/llama.cpp.git C:\Users\NAD\tools\llama.cpp-v1.0.0
#   PyPI gguf==0.19.0 and sentencepiece==0.2.3 (the convert script imports it; the release lists it in
#   requirements/requirements-convert_legacy_llama.txt) installed into the repo's .venv
#   llama-quantize = `llama quantize` inside the official image below (same release)
param(
    [string]$Merged = "C:\Users\NAD\models\cleanops-assistant-merged",
    [string]$OutDir = "C:\Users\NAD\models\gguf",
    [string]$LlamaCpp = "C:\Users\NAD\tools\llama.cpp-v1.0.0",
    [string[]]$Quants = @("Q4_K_M", "Q5_K_M"),
    [string]$Image = "ghcr.io/ggml-org/llama.cpp:server-cuda-v1.0.0-b12359-b1b770d"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force $OutDir | Out-Null
$env:PYTHONUTF8 = "1"
& $py "$LlamaCpp\convert_hf_to_gguf.py" $Merged --outtype q8_0 --outfile "$OutDir\cleanops-assistant-v2-q8_0.gguf"
& $py "$LlamaCpp\convert_hf_to_gguf.py" $Merged --outtype f16 --outfile "$OutDir\cleanops-assistant-v2-f16.gguf"
foreach ($q in $Quants) {
    # quantise from the f16 file (re-quantising q8_0 would stack two roundings)
    docker run --rm -v "${OutDir}:/models" --entrypoint /app/llama $Image quantize `
        /models/cleanops-assistant-v2-f16.gguf /models/cleanops-assistant-v2-$($q.ToLower()).gguf $q
}
