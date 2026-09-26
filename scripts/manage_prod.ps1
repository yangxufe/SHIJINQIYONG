$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'load_runtime.ps1')
Set-Location $projectRoot
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $projectRoot 'manage.py') @args
exit $LASTEXITCODE
