$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'load_runtime.ps1')
Set-Location $projectRoot
$recentFailures = @()
while ($true) {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m scripts.serve_waitress
    $recentFailures = @($recentFailures | Where-Object { $_ -gt (Get-Date).AddMinutes(-5) })
    $recentFailures += Get-Date
    if ($recentFailures.Count -gt 5) {
        throw 'Waitress 在五分钟内反复退出；停止重试以便检查。'
    }
    Start-Sleep -Seconds 2
}
