$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

& '.\.venv\Scripts\python.exe' -m ruff check backend
& '.\.venv\Scripts\python.exe' -m pytest --cov=patchpilot --cov-report=term-missing

Push-Location -LiteralPath 'frontend'
try {
    npm run lint
    npm run build
} finally {
    Pop-Location
}
