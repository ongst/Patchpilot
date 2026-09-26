$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath '.venv')) {
    py -3 -m venv .venv
}

& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'

Push-Location -LiteralPath 'frontend'
try {
    npm install
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env. Add PATCHPILOT_LLM_API_KEY before starting a repair run.' -ForegroundColor Yellow
}

Write-Host 'PatchPilot setup complete.' -ForegroundColor Green
