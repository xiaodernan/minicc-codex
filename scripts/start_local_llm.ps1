# M8-T1331 — start a fully offline local LLM (no Clash, no external endpoint).
#
# Why: the configured external provider requires Clash DNS; the RTX 3060 CUDA
# path crashes llama-server with 0xc0000409 ("device kernel image is invalid").
# The CPU path is slower but actually works, so we pin it explicitly here.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/start_local_llm.ps1
# Then point MINICC_BASE_URL / MINICC_MODEL at the endpoint printed below.

$ErrorActionPreference = "Stop"

$ollama = "C:\Users\18414\AppData\Local\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollama)) {
  Write-Error "ollama.exe not found at $ollama"
}

# Pin CPU-only inference: OLLAMA_NUM_GPU=0 keeps the model off the broken CUDA
# path; VULKAN/CUDA flags are cleared so discovery cannot fall back to them.
$env:OLLAMA_NUM_GPU = "0"
$env:OLLAMA_VULKAN = "false"
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:GGML_VK_VISIBLE_DEVICES -ErrorAction SilentlyContinue

# Already listening? Verify it answers before declaring success.
try {
  $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:11434/api/tags
  if ($r.StatusCode -eq 200) {
    Write-Host "Ollama already answering on http://127.0.0.1:11434 — nothing to do."
    $r.Content | ConvertFrom-Json | Select-Object -ExpandProperty models | ForEach-Object {
      Write-Host ("  model: " + $_.name)
    }
    exit 0
  }
} catch { /* not running — start it below */ }

Write-Host "Starting Ollama in CPU mode (OLLAMA_NUM_GPU=0)..."
$proc = Start-Process -FilePath $ollama -ArgumentList "serve" -PassThru -WindowStyle Hidden
Write-Host ("Ollama started, PID " + $proc.Id)

# Wait for readiness instead of a blind sleep.
$deadline = (Get-Date).AddSeconds(30)
$ok = $false
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 500
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:11434/api/tags
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { /* keep waiting */ }
}
if (-not $ok) {
  Write-Error "Ollama did not answer within 30s — check: Get-Content on its log."
}

Write-Host "READY. OpenAI-compatible endpoint:"
Write-Host "  base_url = http://127.0.0.1:11434/v1"
Write-Host "  model    = qwen2.5:7b"
Write-Host "  api_key  = ollama (any nonempty value)"
Write-Host "Set MINICC_BASE_URL / MINICC_MODEL / MINICC_API_KEY in .env to use it."
