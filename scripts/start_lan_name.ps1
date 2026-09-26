$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$recentFailures = @()
while ($true) {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m scripts.publish_lan_name
    $recentFailures = @($recentFailures | Where-Object { $_ -gt (Get-Date).AddMinutes(-5) })
    $recentFailures += Get-Date
    if ($recentFailures.Count -gt 5) {
        throw '局域网名称发布在五分钟内反复退出；停止重试以便检查。'
    }
    Start-Sleep -Seconds 2
}
