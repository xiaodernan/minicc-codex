# M8-T1331 / M8-T1338 — start a fully offline local LLM (no Clash, no external endpoint).
#
# Why: the configured external provider requires Clash DNS; the RTX 3060 CUDA
# path crashes llama-server with 0xc0000409 ("device kernel image is invalid").
# The CPU path is slower but actually works, so we pin it explicitly here.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/start_local_llm.ps1
# Prints the endpoint; minicc's .env already points at it.

$ErrorActionPreference = "Stop"

$ollama = "C:\Users\18414\AppData\Local\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollama)) {
  Write-Error "ollama.exe not found at $ollama"
}

# Pin CPU-only inference so a restart (including the Startup tray app) cannot
# fall back to the crashing CUDA path. Persist at User scope AND set now.
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU", "0", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_VULKAN", "false", "User")
$env:OLLAMA_NUM_GPU = "0"
$env:OLLAMA_VULKAN = "false"
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:GGML_VK_VISIBLE_DEVICES -ErrorAction SilentlyContinue

# M8-T1338: /api/tags answers 200 even in the crashing CUDA mode, so it cannot
# prove readiness. A tiny chat request actually loads the model and infers.
function Invoke-InferenceProbe {
  param([int]$TimeoutSec = 60)
  $body = '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"Reply only: OK"}],"max_tokens":5}'
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSec `
      -Uri "http://127.0.0.1:11434/v1/chat/completions" `
      -Method Post -ContentType "application/json" -Body $body
    return ($r.StatusCode -eq 200 -and $r.Content -match "OK")
  } catch {
    return $false
  }
}

# Already listening? Tags alone are not enough — require a real inference.
try {
  $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:11434/api/tags
  if ($r.StatusCode -eq 200) {
    if (Invoke-InferenceProbe) {
      Write-Host "Ollama already answering and inferring on http://127.0.0.1:11434 — nothing to do."
      $r.Content | ConvertFrom-Json | Select-Object -ExpandProperty models | ForEach-Object {
        Write-Host ("  model: " + $_.name)
      }
      exit 0
    }
    Write-Host "Ollama is up but inference failed (likely CUDA mode). Restart it in CPU mode:"
    Write-Host "  Get-Process ollama | Stop-Process -Force; then re-run this script."
    exit 2
  }
} catch {
  # Nothing listening — start it below. PowerShell comments use the hash sign.
}

Write-Host "Starting Ollama in CPU mode (OLLAMA_NUM_GPU=0)..."
$proc = Start-Process -FilePath $ollama -ArgumentList "serve" -PassThru -WindowStyle Hidden
Write-Host ("Ollama started, PID " + $proc.Id)

# Wait for readiness with a real inference probe, not a blind sleep.
$deadline = (Get-Date).AddSeconds(60)
$ok = $false
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 500
  if (Invoke-InferenceProbe -TimeoutSec 20) { $ok = $true; break }
}
if (-not $ok) {
  Write-Error "Ollama did not become ready for inference within 60s — check its log."
}

Write-Host "READY (inference verified). OpenAI-compatible endpoint:"
Write-Host "  base_url = http://127.0.0.1:11434/v1"
Write-Host "  model    = qwen2.5:7b"
Write-Host "  api_key  = ollama (any nonempty value)"
Write-Host "CPU mode persisted to User env; restarts keep it."
