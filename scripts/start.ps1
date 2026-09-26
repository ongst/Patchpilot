$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Run scripts\setup.ps1 first.'
}

$Backend = Start-Process -FilePath $Python -ArgumentList '-m', 'uvicorn', 'patchpilot.main:app', '--host', '127.0.0.1', '--port', '8000' -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
$Frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run', 'dev' -WorkingDirectory (Join-Path $ProjectRoot 'frontend') -WindowStyle Hidden -PassThru

Write-Host 'PatchPilot API: http://127.0.0.1:8000/docs'
Write-Host 'PatchPilot UI:  http://127.0.0.1:5173'
Write-Host 'Press Ctrl+C to stop both services.'

try {
    while (-not $Backend.HasExited -and -not $Frontend.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    if (-not $Backend.HasExited) { Stop-Process -Id $Backend.Id }
    if (-not $Frontend.HasExited) { Stop-Process -Id $Frontend.Id }
}

