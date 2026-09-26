$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '需要以管理员身份运行此脚本；当前未修改服务。'
}
$service = Get-CimInstance Win32_Service -Filter "Name='ShiJinQiYongCaddy'"
if (-not $service -or $service.StartName -ne 'NT AUTHORITY\LocalService' -or $service.PathName -notlike '*\ShiJinQiYong\Caddy\caddy.exe*') {
    throw 'Caddy 服务身份或程序路径与本项目记录不符；未修改。'
}
Set-Service -Name 'ShiJinQiYongCaddy' -StartupType Automatic
$updated = Get-CimInstance Win32_Service -Filter "Name='ShiJinQiYongCaddy'"
if ($updated.StartMode -ne 'Auto') {
    throw '服务启动方式核对失败。'
}
Write-Output '食尽其用 Caddy 服务已设为自动启动。'
