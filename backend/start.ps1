param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { throw 'Create the project .venv and install backend/requirements.txt first. See README.md.' }
Push-Location $PSScriptRoot
try {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE" }
} finally { Pop-Location }
