param([switch]$Once, [switch]$DryRun, [string]$TrustedFile)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if ($TrustedFile -and -not $DryRun) { throw 'TrustedFile override is allowed only for a dry run.' }
$trustedFile = if ($TrustedFile) { $TrustedFile } else { Join-Path $root 'trusted-networks.json' }
$stateFile = Join-Path $root 'active.json'
$statusFile = Join-Path $root 'last_status.txt'
$ruleName = 'ShiJinQiYong-Caddy-HTTPS-8443-WLAN'
$mdnsRuleName = 'ShiJinQiYong-LanName-5353-WLAN'
$serviceName = 'ShiJinQiYongCaddy'
$caddyPath = 'C:\Program Files\ShiJinQiYong\Caddy\caddy.exe'
$pythonPath = 'C:\Users\Yangf\miniconda3\python.exe'
$wlanGuid = (Get-NetAdapter -Name 'WLAN' -ErrorAction Stop).InterfaceGuid.ToString()

function Get-CurrentWlan {
    $lines = & netsh wlan show interfaces
    if ($LASTEXITCODE -ne 0) { return $null }
    $joined = $lines -join "`n"
    $ssidMatch = [regex]::Match($joined, '(?m)^\s*SSID\s*:\s*(.+?)\s*$')
    $bssidMatch = [regex]::Match($joined, '(?m)^\s*AP BSSID\s*:\s*([0-9a-fA-F:]{17})\s*$')
    if (-not $ssidMatch.Success -or -not $bssidMatch.Success) { return $null }
    $address = @(Get-NetIPAddress -InterfaceAlias 'WLAN' -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.AddressState -eq 'Preferred' -and $_.IPAddress -match '^\d+\.\d+\.\d+\.\d+$' })
    if ($address.Count -ne 1) { return $null }
    return [pscustomobject]@{
        ssid = $ssidMatch.Groups[1].Value.Trim()
        bssid = $bssidMatch.Groups[1].Value.ToLowerInvariant()
        ip = $address[0].IPAddress
    }
}

function Test-TrustedWlan($current, $networks) {
    if (-not $current) { return $false }
    foreach ($entry in $networks) {
        if ($current.ssid -cne $entry.ssid) { continue }
        foreach ($bssid in $entry.bssids) {
            if ($current.bssid -eq $bssid.ToLowerInvariant()) { return $true }
        }
    }
    return $false
}

function Write-ActiveState($ip) {
    $payload = @{ ip = $ip; interface_guid = $wlanGuid; updated_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() } | ConvertTo-Json -Compress
    $temporary = Join-Path $root ('active-' + [guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($temporary, $payload, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $stateFile -Force
}

function Assert-ManagedBoundary {
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction Stop
    $port = $rule | Get-NetFirewallPortFilter
    $program = $rule | Get-NetFirewallApplicationFilter
    $interface = $rule | Get-NetFirewallInterfaceFilter
    $service = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
    if ($rule.Direction -ne 'Inbound' -or $rule.Action -ne 'Allow' -or $rule.Profile -ne 'Public' -or
        $port.Protocol -ne 'TCP' -or $port.LocalPort -ne '8443' -or
        $program.Program -ne $caddyPath -or $interface.InterfaceAlias -ne 'WLAN' -or
        -not $service -or $service.StartName -ne 'NT AUTHORITY\LocalService' -or
        $service.PathName -notlike '*\ShiJinQiYong\Caddy\caddy.exe*') {
        throw 'Caddy service or firewall boundary changed unexpectedly.'
    }
    $mdns = Get-NetFirewallRule -Name $mdnsRuleName -ErrorAction Stop
    $mdnsPort = $mdns | Get-NetFirewallPortFilter
    if ($mdns.Direction -ne 'Inbound' -or $mdns.Action -ne 'Allow' -or $mdns.Profile -ne 'Public' -or
        $mdnsPort.Protocol -ne 'UDP' -or $mdnsPort.LocalPort -ne '5353' -or
        (($mdns | Get-NetFirewallApplicationFilter).Program) -ne $pythonPath -or
        (($mdns | Get-NetFirewallInterfaceFilter).InterfaceAlias) -ne 'WLAN' -or
        (($mdns | Get-NetFirewallAddressFilter).RemoteAddress) -ne 'LocalSubnet') {
        throw 'mDNS firewall boundary changed unexpectedly.'
    }
}

function Close-Entrance {
    Disable-NetFirewallRule -Name $ruleName -ErrorAction Stop
    Disable-NetFirewallRule -Name $mdnsRuleName -ErrorAction Stop
    Write-ActiveState $null
    if ((Get-Service -Name $serviceName -ErrorAction Stop).Status -ne 'Stopped') {
        Stop-Service -Name $serviceName -ErrorAction Stop
    }
}

function Open-Entrance($ip) {
    Disable-NetFirewallRule -Name $ruleName -ErrorAction Stop
    Disable-NetFirewallRule -Name $mdnsRuleName -ErrorAction Stop
    Write-ActiveState $null
    Get-NetFirewallRule -Name $ruleName | Get-NetFirewallAddressFilter |
        Set-NetFirewallAddressFilter -LocalAddress $ip -RemoteAddress LocalSubnet -ErrorAction Stop
    if ((Get-Service -Name $serviceName -ErrorAction Stop).Status -ne 'Running') {
        Start-Service -Name $serviceName -ErrorAction Stop
    }
    $listening = $false
    for ($i = 0; $i -lt 20; $i++) {
        $servicePid = (Get-CimInstance Win32_Service -Filter "Name='$serviceName'").ProcessId
        $socket = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -eq $servicePid -and $_.LocalAddress -in @('0.0.0.0', '::', $ip) }
        if ($socket) {
            $client = [Net.Sockets.TcpClient]::new()
            try {
                $attempt = $client.BeginConnect($ip, 8443, $null, $null)
                if ($attempt.AsyncWaitHandle.WaitOne(300)) {
                    $client.EndConnect($attempt)
                    $listening = $true
                    break
                }
            } catch { } finally { $client.Dispose() }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $listening) { throw 'Caddy process did not accept the current WLAN IPv4 address on port 8443.' }
    Enable-NetFirewallRule -Name $ruleName -ErrorAction Stop
    Enable-NetFirewallRule -Name $mdnsRuleName -ErrorAction Stop
    Write-ActiveState $ip
}

$trusted = (Get-Content -LiteralPath $trustedFile -Raw | ConvertFrom-Json).networks
if (-not $trusted) { throw 'No trusted WLAN entries configured.' }
if (-not $DryRun) { Assert-ManagedBoundary }
$lastIp = $null
do {
    try {
        $current = Get-CurrentWlan
        $trustedNow = Test-TrustedWlan $current $trusted
        if ($DryRun) {
            if ($trustedNow) { Write-Output "trusted=$($current.ip)" } else { Write-Output 'trusted=none' }
        } elseif ($trustedNow) {
            $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction Stop
            $service = Get-Service -Name $serviceName -ErrorAction Stop
            if ($lastIp -ne $current.ip -or $rule.Enabled -ne 'True' -or $service.Status -ne 'Running') {
                Open-Entrance $current.ip
                $lastIp = $current.ip
                [IO.File]::WriteAllText($statusFile, 'active', [Text.UTF8Encoding]::new($false))
            } else {
                Write-ActiveState $current.ip
            }
        } else {
            Close-Entrance
            $lastIp = $null
            [IO.File]::WriteAllText($statusFile, 'untrusted', [Text.UTF8Encoding]::new($false))
        }
    } catch {
        if ($DryRun) { throw }
        $reason = $_.Exception.Message
        try { [IO.File]::WriteAllText($statusFile, 'error=' + $reason, [Text.UTF8Encoding]::new($false)) } catch { }
        try { Close-Entrance } catch { }
        $lastIp = $null
    }
    if (-not $Once) { Start-Sleep -Seconds 4 }
} while (-not $Once)
