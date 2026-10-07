param([Parameter(Mandatory=$true)][string]$Address)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$rows = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq $Address -and $_.AddressState -eq 'Preferred' })
if ($rows.Count -ne 1) { throw '原网络地址不可用。' }
$row = $rows[0]
$network = Get-NetConnectionProfile -InterfaceIndex $row.InterfaceIndex
@{ ip=$row.IPAddress; prefix=$row.PrefixLength; interface=$row.InterfaceAlias; network=$network.Name } | ConvertTo-Json -Compress
