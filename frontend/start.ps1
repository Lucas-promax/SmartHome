param([int]$Port = 3001)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & npm.cmd run dev -- --host 127.0.0.1 --port $Port --strictPort
    if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
} finally { Pop-Location }
