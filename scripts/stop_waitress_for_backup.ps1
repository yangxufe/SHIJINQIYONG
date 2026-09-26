$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'ShiJinQiYong-Waitress' -ErrorAction Stop
if ($task.State -eq 'Running') {
    Stop-ScheduledTask -TaskName 'ShiJinQiYong-Waitress' -ErrorAction Stop
}
$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (-not $serverProcess -or $serverProcess.CommandLine -notmatch 'python\.exe" -m scripts\.serve_waitress$') {
        throw '8000 端口由未知进程占用；未停止该进程。'
    }
    Stop-Process -Id $listener.OwningProcess -ErrorAction Stop
}
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
        Write-Output 'Waitress 已停止；现在可以执行 backup_household。'
        exit 0
    }
    Start-Sleep -Milliseconds 250
}
throw 'Waitress 仍在监听 8000；不要运行备份。'
