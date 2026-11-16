param([ValidateRange(1, 65535)][int]$Port = 3001)
$ErrorActionPreference = 'Stop'
Write-Host "SmartHome: http://localhost:$Port"
Write-Host 'Keep this window open. Press Ctrl+C to stop the SSH tunnel.'
while ($true) {
    & ssh -N -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -L "127.0.0.1:${Port}:127.0.0.1:8000" orangepi
    Write-Host "SSH exited ($LASTEXITCODE). Reconnecting in 3 seconds..."
    Start-Sleep -Seconds 3
}
