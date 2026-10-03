$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$venvHomeLine = Get-Content -LiteralPath (Join-Path $projectRoot '.venv\pyvenv.cfg') |
    Where-Object { $_ -match '^home\s*=\s*(.+)$' } | Select-Object -First 1
if (-not $venvHomeLine) { throw '无法核对本项目 Python 解释器；未停止进程。' }
$venvHome = ($venvHomeLine -replace '^home\s*=\s*', '').Trim()
$knownInterpreters = @(
    [IO.Path]::GetFullPath((Join-Path $projectRoot '.venv\Scripts\python.exe')),
    [IO.Path]::GetFullPath((Join-Path $venvHome 'python.exe'))
)
function Test-KnownWaitressProcess($serverProcess) {
    return ($serverProcess -and $serverProcess.ExecutablePath -in $knownInterpreters -and
        $serverProcess.CommandLine -match '\s-m\s+scripts\.serve_waitress\s*$')
}

# Capture before stopping the task: the Windows venv launcher can leave its
# base-interpreter child alive. Include only validated Waitress processes.
$snapshots = @{}
$listeners = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
    $serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (-not (Test-KnownWaitressProcess $serverProcess)) {
        throw '8000 端口由未知进程占用；未停止该进程。'
    }
    $snapshots[$serverProcess.ProcessId] = $serverProcess
    $ancestor = $serverProcess
    for ($depth = 0; $depth -lt 8; $depth++) {
        $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId=$($ancestor.ParentProcessId)"
        if (-not (Test-KnownWaitressProcess $ancestor)) { break }
        $snapshots[$ancestor.ProcessId] = $ancestor
    }
}
for ($depth = 0; $depth -lt 8; $depth++) {
    $added = $false
    foreach ($snapshot in @($snapshots.Values)) {
        foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($snapshot.ProcessId)")) {
            if ((Test-KnownWaitressProcess $child) -and -not $snapshots.ContainsKey($child.ProcessId)) {
                $snapshots[$child.ProcessId] = $child
                $added = $true
            }
        }
    }
    if (-not $added) { break }
}
$task = Get-ScheduledTask -TaskName 'ShiJinQiYong-Waitress' -ErrorAction Stop
if ($task.State -eq 'Running') {
    Stop-ScheduledTask -TaskName 'ShiJinQiYong-Waitress' -ErrorAction Stop
}
foreach ($snapshot in @($snapshots.Values)) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($snapshot.ProcessId)"
    if ($current -and $current.CreationDate -eq $snapshot.CreationDate -and (Test-KnownWaitressProcess $current)) {
        Stop-Process -Id $current.ProcessId -ErrorAction Stop
    }
}
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
        Write-Output 'Waitress 已停止；现在可以执行 backup_household。'
        exit 0
    }
    Start-Sleep -Milliseconds 250
}
throw 'Waitress 仍在监听 8000；不要运行备份。'
