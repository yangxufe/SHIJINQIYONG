$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeFile = Join-Path $projectRoot 'data\runtime.env'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $runtimeFile) { throw 'Runtime configuration already exists; it was not overwritten.' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Virtual environment is missing.' }
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'data') -Force | Out-Null
$secret = & $python -c 'import secrets; print(secrets.token_urlsafe(64))'
if ($LASTEXITCODE -ne 0 -or $secret.Length -lt 50) { throw 'Could not generate a strong secret.' }
$dataPath = (Join-Path $projectRoot 'data').Replace('\', '/')
$content = @(
    "SHIJIN_SECRET_KEY=$secret"
    'SHIJIN_ALLOWED_HOSTS=192.168.110.146'
    'SHIJIN_CSRF_TRUSTED_ORIGINS=https://192.168.110.146:8443'
    'SHIJIN_TIME_ZONE=Asia/Shanghai'
    "SHIJIN_DATA_DIR=$dataPath"
    'SHIJIN_STATIC_ROOT=C:/ProgramData/ShiJinQiYong/static'
)
[System.IO.File]::WriteAllLines($runtimeFile, $content, [System.Text.UTF8Encoding]::new($false))
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($user, 'FullControl', 'Allow')))
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('NT AUTHORITY\SYSTEM', 'FullControl', 'Allow')))
Set-Acl -LiteralPath $runtimeFile -AclObject $acl
Write-Output 'Created private data/runtime.env with a random secret; value not displayed.'
