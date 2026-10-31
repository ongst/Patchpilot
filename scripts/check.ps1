$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

& '.\.venv\Scripts\python.exe' -m ruff check backend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$PytestTemp = Join-Path ([System.IO.Path]::GetTempPath()) ("patchpilot-pytest-" + [guid]::NewGuid().ToString("N"))
& '.\.venv\Scripts\python.exe' -m pytest --cov=patchpilot --cov-report=term-missing --basetemp="$PytestTemp" -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location -LiteralPath 'frontend'
try {
    npm run lint
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "All checks passed!"
