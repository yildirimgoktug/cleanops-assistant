# Serve a GGUF with the official llama.cpp server image, OpenAI-compatible API on 127.0.0.1 ONLY.
#   .\scripts\serve_llama_server.ps1 start [-Gguf cleanops-assistant-v2-q8_0.gguf]
#   .\scripts\serve_llama_server.ps1 stop
# --reasoning off: the model was trained with the Qwen3 template's EMPTY think block (enable_thinking=False), so the
# server must render the prompt that way; with the template default the model's tool call would land in
# `reasoning_content` and `tool_calls` would stay empty (this is also why LM Studio could not be used).
param(
    [Parameter(Position = 0)][ValidateSet("start", "stop", "status")][string]$Action = "status",
    [string]$Gguf = "cleanops-assistant-v2-q8_0.gguf",
    [string]$ModelDir = "C:\Users\NAD\models\gguf",
    [int]$Port = 8080,
    [int]$Context = 8192,
    [string]$Image = "ghcr.io/ggml-org/llama.cpp:server-cuda-v1.0.0-b12359-b1b770d"
)
$name = "cleanops-llm"
switch ($Action) {
    "start" {
        docker rm -f $name 2>$null | Out-Null
        docker run -d --name $name --gpus all -p "127.0.0.1:${Port}:8080" -v "${ModelDir}:/models:ro" $Image `
            --model "/models/$Gguf" --alias cleanops-assistant --host 0.0.0.0 --port 8080 `
            -ngl 99 -c $Context --parallel 1 --jinja --reasoning off
        for ($i = 0; $i -lt 60; $i++) {
            try { if ((Invoke-RestMethod "http://127.0.0.1:$Port/health").status -eq "ok") { "ready on http://127.0.0.1:$Port"; break } } catch {}
            Start-Sleep 2
        }
    }
    "stop" { docker rm -f $name }
    "status" { docker ps --filter "name=$name" --format "{{.Names}} {{.Status}} {{.Ports}}" }
}
