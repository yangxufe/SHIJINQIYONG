$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew

foreach ($entry in @(
    @{ Name = 'ShiJinQiYong-Waitress'; Script = 'start_waitress.ps1' }
)) {
    if (Get-ScheduledTask -TaskName $entry.Name -ErrorAction SilentlyContinue) {
        throw "计划任务 $($entry.Name) 已存在；请先核对，不覆盖。"
    }
    $scriptPath = Join-Path $PSScriptRoot $entry.Script
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "启动脚本 $($entry.Script) 不存在。"
    }
    $action = New-ScheduledTaskAction -Execute $powershell -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`"" -WorkingDirectory $projectRoot
    Register-ScheduledTask -TaskName $entry.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description '食尽其用：当前 Windows 用户登录后启动本机服务' | Out-Null
    Write-Output "已建立当前用户登录任务：$($entry.Name)"
}
