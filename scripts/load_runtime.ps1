$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeFile = Join-Path $projectRoot 'data\runtime.env'
if (-not (Test-Path -LiteralPath $runtimeFile)) {
    throw 'data/runtime.env is missing. Run scripts/initialize_runtime.ps1 first.'
}
$allowed = @('SHIJIN_SECRET_KEY', 'SHIJIN_ALLOWED_HOSTS', 'SHIJIN_CSRF_TRUSTED_ORIGINS', 'SHIJIN_TIME_ZONE', 'SHIJIN_DATA_DIR', 'SHIJIN_STATIC_ROOT', 'SHIJIN_RECIPE_PROVIDER', 'SHIJIN_RECIPE_MODEL', 'SHIJIN_RECIPE_API_KEY', 'SHIJIN_YOLO_MODEL')
foreach ($line in Get-Content -LiteralPath $runtimeFile) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) { continue }
    if ($line -notmatch '^([A-Z_]+)=(.*)$') { throw 'Invalid runtime configuration line.' }
    $name = $Matches[1]
    $value = $Matches[2]
    if ($name -notin $allowed -or [string]::IsNullOrWhiteSpace($value)) {
        throw 'Invalid runtime configuration value.'
    }
    Set-Item -Path "Env:$name" -Value $value
}
$env:DJANGO_SETTINGS_MODULE = 'config.settings.prod'
