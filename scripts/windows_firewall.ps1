param([Parameter(Mandatory=$true)][string]$LanFile)
$ErrorActionPreference = 'Stop'
try {
    $lan = Get-Content -LiteralPath $LanFile -Raw | ConvertFrom-Json
    $profileDir = Split-Path ([IO.Path]::GetFullPath($LanFile)) -Parent
    $exe = [IO.Path]::GetFullPath($lan.caddy)
    if (-not $exe.StartsWith((Join-Path $profileDir 'tools') + '\', [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $exe) -or $lan.rule -notmatch '^ShiJinQiYong-[0-9A-F]{20}$') { throw '非法防火墙配置。' }
    if ($lan.ip -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -or $lan.cidr -notmatch '^\d+\.\d+\.\d+\.\d+/(1[6-9]|2[0-9]|30)$' -or [int]$lan.port -lt 1024 -or [int]$lan.port -gt 65535) { throw '非法网络范围。' }
    $actual = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias $lan.interface | Where-Object { $_.IPAddress -eq $lan.ip -and $_.AddressState -eq 'Preferred' })
    if ($actual.Count -ne 1) { throw '网卡地址已变化，未开放。' }
    $bytes = ([Net.IPAddress]::Parse($lan.ip)).GetAddressBytes()
    $prefix = $actual[0].PrefixLength
    for ($i=0; $i -lt 4; $i++) { $bits = [Math]::Min(8,[Math]::Max(0,$prefix-$i*8)); $bytes[$i] = $bytes[$i] -band (256-[Math]::Pow(2,8-$bits)) }
    $expected = ([Net.IPAddress]::new($bytes)).ToString() + '/' + $prefix
    if ($lan.cidr -ne $expected) { throw '子网与实际网卡不一致。' }
    $existing = Get-NetFirewallRule -Name $lan.rule -ErrorAction SilentlyContinue
    if ($existing) { Remove-NetFirewallRule -Name $lan.rule }
    New-NetFirewallRule -Name $lan.rule -DisplayName $lan.rule -Direction Inbound -Action Allow -Program $exe -Protocol TCP -LocalPort $lan.port -LocalAddress $lan.ip -RemoteAddress $lan.cidr -InterfaceAlias $lan.interface -Profile Any | Out-Null
    exit 0
} catch { Write-Error $_.Exception.Message; exit 1 }
