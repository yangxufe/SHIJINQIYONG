$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'load_runtime.ps1')
Set-Location $projectRoot
if (-not $env:SHIJIN_RECIPE_PROVIDER -or $env:SHIJIN_RECIPE_PROVIDER -eq 'off') {
    throw '菜谱模型尚未由管理员启用；工作进程未启动。'
}
$recentFailures = @()
while ($true) {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') manage.py run_recipe_worker --settings=config.settings.prod
    $recentFailures = @($recentFailures | Where-Object { $_ -gt (Get-Date).AddMinutes(-5) })
    $recentFailures += Get-Date
    if ($recentFailures.Count -gt 5) {
        throw '菜谱工作进程在五分钟内反复退出；停止重试。'
    }
    Start-Sleep -Seconds 2
}
