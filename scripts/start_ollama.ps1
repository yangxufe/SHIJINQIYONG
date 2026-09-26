$ErrorActionPreference = 'Stop'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollama)) {
    throw '本机 Ollama 程序不存在。'
}
$recentFailures = @()
while ($true) {
    & $ollama serve
    $recentFailures = @($recentFailures | Where-Object { $_ -gt (Get-Date).AddMinutes(-5) })
    $recentFailures += Get-Date
    if ($recentFailures.Count -gt 5) {
        throw 'Ollama 在五分钟内反复退出；停止重试以便检查。'
    }
    Start-Sleep -Seconds 2
}
