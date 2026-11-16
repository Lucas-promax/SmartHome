param(
    [ValidateRange(1, 65535)][int]$FrontendPort = 3001,
    [ValidateRange(1, 65535)][int]$BackendPort = 8000
)

$ErrorActionPreference = 'Stop'
if ($FrontendPort -eq $BackendPort) { throw 'Frontend and backend ports must differ.' }
if (-not (Test-Path (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'))) {
    throw 'Missing .venv. Install backend dependencies first.'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node.js / npm is not installed.' }
if (-not (Test-Path (Join-Path $PSScriptRoot 'frontend/node_modules'))) {
    throw 'Run npm.cmd install in frontend first.'
}
foreach ($port in @($BackendPort, $FrontendPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing service or choose another port."
    }
}

$jobs = @()
try {
    $jobs += Start-Job -Name SmartHomeBackend -ArgumentList $PSScriptRoot, $BackendPort -ScriptBlock {
        param($root, $port)
        Set-Location (Join-Path $root 'backend')
        & (Join-Path $root '.venv/Scripts/python.exe') -m uvicorn app.main:app --host 127.0.0.1 --port $port
        if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE" }
    }
    $jobs += Start-Job -Name SmartHomeFrontend -ArgumentList $PSScriptRoot, $FrontendPort -ScriptBlock {
        param($root, $port)
        Set-Location (Join-Path $root 'frontend')
        & npm.cmd run dev -- --host 127.0.0.1 --port $port --strictPort
        if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
    }
    Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
    Write-Host "Backend:  http://127.0.0.1:$BackendPort"
    Write-Host 'Starting services. Press Ctrl+C to stop both.'
    while ($true) {
        foreach ($job in $jobs) {
            Receive-Job $job -ErrorAction Continue
            if ($job.State -ne 'Running') { throw "$($job.Name) stopped ($($job.State))." }
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    foreach ($job in $jobs) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    }
}
