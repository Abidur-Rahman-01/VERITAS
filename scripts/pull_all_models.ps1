# Pull all requested Ollama models
$env:Path = "$env:LOCALAPPDATA\Programs\Ollama;" + $env:Path

Write-Host "Checking Ollama version..." -ForegroundColor Cyan
& ollama --version

$models = @(
    "tinyllama",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "llama3.2:3b",
    "phi3.5",
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma3:4b",
    "gemma3:12b",
    "qwen2.5:14b"
)

foreach ($model in $models) {
    Write-Host "`n======================================================" -ForegroundColor Yellow
    Write-Host "Pulling: $model" -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor Yellow
    & ollama pull $model
}

Write-Host "`nFinished! Currently installed models:" -ForegroundColor Cyan
& ollama list
