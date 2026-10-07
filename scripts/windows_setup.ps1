[CmdletBinding()]
param(
    [ValidateSet('Menu','Local','Lan','Prepare','Smoke','Account','Backup')][string]$Mode = 'Menu',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'ShiJinQiYong'),
    [string]$TimeZone = '',
    [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "命令执行失败（退出码 $LASTEXITCODE），安装已停止。" }
}

function Get-VerifiedDownload {
    param($Item, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm $Item.algorithm).Hash -eq $Item.hash) { return }
        throw "缓存文件校验失败：$Destination。请检查后移走此文件，再运行；不会执行它。"
    }
    Write-Host ('从官方来源下载：' + $Item.url)
    $partial = "$Destination.partial"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $Item.url -OutFile $partial -TimeoutSec 300
    if ((Get-FileHash -LiteralPath $partial -Algorithm $Item.algorithm).Hash -ne $Item.hash) {
        throw '下载校验失败；文件未执行。请重试或核对官方发行版本。'
    }
    Move-Item -LiteralPath $partial -Destination $Destination
}

function Test-Python {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    & $Path -I -c "import sys,struct,venv,ssl;sys.exit(0 if (3,13,16)<=sys.version_info[:3]<(3,14) and struct.calcsize('P')==8 else 1)" 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-ArchiveExecutable {
    param([string]$Archive, [string]$Entry, [string]$File)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    $stream = $null
    $digest = [Security.Cryptography.SHA256]::Create()
    try {
        $item = $zip.GetEntry($Entry)
        if (-not $item) { throw '官方压缩包缺少预期程序。' }
        $stream = $item.Open()
        $expected = ([BitConverter]::ToString($digest.ComputeHash($stream))).Replace('-','')
        if ((Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash -ne $expected) { throw "程序与已校验的官方压缩包不一致：$File。未执行。" }
    } finally {
        if ($stream) { $stream.Dispose() }
        $digest.Dispose()
        $zip.Dispose()
    }
}

function Protect-Directory {
    param([string]$Path)
    $userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $Path /inheritance:r /grant:r "*$($userSid):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '无法限制私有目录访问权限。' }
    $acl = Get-Acl -LiteralPath $Path
    foreach ($rule in $acl.Access) {
        $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($rule.AccessControlType -eq 'Allow' -and $sid -notin @($userSid,'S-1-5-18')) { throw '私有目录仍有其他用户的显式访问权限，安装已停止。' }
    }

}

$mutex = $null
$locked = $false
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
        throw '当前自动安装支持 Windows 10/11 x64；32 位或原生 ARM64 尚未验证。'
    }
    if ([Environment]::OSVersion.Version.Major -lt 10) { throw '需要 Windows 10/11。' }
    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    if ($InstallRoot.StartsWith('\\') -or $InstallRoot -match '["$`\r\n]') { throw '安装目录必须是本机普通目录，且不能包含引号、美元符号、反引号或换行。' }
    foreach ($sync in @($env:OneDrive, $env:OneDriveCommercial, $env:OneDriveConsumer)) {
        if ($sync -and ($InstallRoot -eq $sync -or $InstallRoot.StartsWith($sync.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase))) { throw '私有数据不能放入 OneDrive 同步目录。' }
    }
    $ancestor = $InstallRoot
    while ($ancestor) {
        if ((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '安装目录及其父目录不能是链接或重解析点。' }
        $ancestor = Split-Path $ancestor -Parent
    }
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($InstallRoot))
    if ($drive.DriveType -ne 'Fixed' -or $drive.DriveFormat -ne 'NTFS') { throw '请选择本机 NTFS 磁盘，不能在网盘/共享盘上运行数据库。' }
    if ($drive.AvailableFreeSpace -lt 2GB) { throw '磁盘可用空间不足 2 GB。' }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Protect-Directory $InstallRoot
    $hash = [Security.Cryptography.SHA256]::Create()
    $profileId = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($InstallRoot.ToLowerInvariant())))).Replace('-','').Substring(0,20)
    $hash.Dispose()
    $mutex = [Threading.Mutex]::new($false, ('Local\ShiJinQiYong-' + $profileId))
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw '此家庭实例已有运行/安装窗口。请先在原窗口按 Ctrl+C 停止，避免同时迁移或启动。' }

    Write-Host "食尽其用 · Windows 自动部署`n程序：$projectRoot`n私有数据：$InstallRoot"
    if ($Mode -eq 'Menu') {
        Write-Host '1 启动本机（默认）  2 启动可信家庭局域网  3 账号维护  4 备份'
        $selection = Read-Host '请选择，回车为 1'
        $Mode = switch ($selection) { '2' {'Lan'} '3' {'Account'} '4' {'Backup'} '' {'Local'} '1' {'Local'} default { throw '选择无效。' } }
    }
    if ($NonInteractive -and $Mode -notin @('Prepare','Smoke')) { throw '非交互模式仅用于准备或隔离冒烟检查，不能替用户信任证书或开放网络。' }
    $first = -not (Test-Path -LiteralPath (Join-Path $InstallRoot 'profile.json'))
    if ($first -and (Test-Path -LiteralPath (Join-Path $projectRoot 'data\runtime.env')) -and -not $NonInteractive) {
        Write-Host '检测到此源码目录有旧版运行配置。旧家庭继续使用原服务；此入口会建立独立家庭，不复制或覆盖旧数据库。'
        if ((Read-Host '确认要建立独立家庭请输入 NEW，其他输入退出') -cne 'NEW') { throw '已退出，旧安装保持原样。' }
    }
    if ($first -and -not $TimeZone) {
        if ($NonInteractive) { throw '首次非交互准备须传 -TimeZone，例如实际家庭 IANA 时区。' }
        Write-Host ('Windows 当前时区：' + (Get-TimeZone).Id)
        $TimeZone = Read-Host '确认家庭 IANA 时区（例如 Asia/Shanghai、Europe/London；不能留空）'
    }
    $downloads = Get-Content -LiteralPath (Join-Path $projectRoot 'config\windows-downloads.json') -Raw | ConvertFrom-Json
    $toolsDir = Join-Path $InstallRoot 'tools'
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    $pythonDir = Join-Path $toolsDir ('python-' + $downloads.python.version)
    $python = Join-Path $pythonDir 'tools\python.exe'
    $pythonArchive = Join-Path $toolsDir ('python-' + $downloads.python.version + '.zip')
    Get-VerifiedDownload $downloads.python $pythonArchive
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Host '准备 Python 官方 NuGet 运行环境（无需系统 MSI、PATH 或预装 Python）……'
        Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonDir -Force
    }
    Test-ArchiveExecutable $pythonArchive 'tools/python.exe' $python
    $signatureMarker = Join-Path $pythonDir '.signature-verified'
    if (-not (Test-Path -LiteralPath $signatureMarker)) {
        $signature = Get-AuthenticodeSignature -LiteralPath $python
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python 可执行文件的官方数字签名未通过。' }
        [IO.File]::WriteAllText($signatureMarker, $downloads.python.hash)
    }
    if (-not (Test-Python $python)) { throw '官方 Python 运行环境验证失败，不能继续。' }
    $lockHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'requirements.lock') -Algorithm SHA256).Hash.Substring(0,16)
    $venv = Join-Path $InstallRoot ('venvs\py313-' + $lockHash)
    $appPython = Join-Path $venv 'Scripts\python.exe'
    $ready = Join-Path $venv '.ready'
    if (-not (Test-Path -LiteralPath $ready)) {
        Invoke-Checked $python @('-m','venv',$venv)
        Invoke-Checked $appPython @('-m','pip','--isolated','install','--disable-pip-version-check','--only-binary=:all:','--index-url','https://pypi.org/simple','-r',(Join-Path $projectRoot 'requirements.lock'))
        Invoke-Checked $appPython @('-m','pip','check')
        & $appPython -c 'import django,waitress,argon2,PIL,onnxruntime,numpy'
        if ($LASTEXITCODE -ne 0) {
            Write-Host '检查到基础 DLL/模块载入失败，准备 Microsoft VC++ x64 运行库……'
            $vcInstaller = Join-Path $toolsDir 'vc_redist.x64.exe'
            Invoke-WebRequest -UseBasicParsing 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $vcInstaller -TimeoutSec 300
            $vcSignature = Get-AuthenticodeSignature -LiteralPath $vcInstaller
            if ($vcSignature.Status -ne 'Valid' -or $vcSignature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { throw 'VC++ 运行库签名验证失败，未执行。' }
            $vcProcess = Start-Process -FilePath $vcInstaller -ArgumentList '/install /quiet /norestart' -WindowStyle Hidden -Wait -PassThru
            if ($vcProcess.ExitCode -notin @(0,3010,1638)) { throw "VC++ 运行库安装失败：$($vcProcess.ExitCode)。" }
            Invoke-Checked $appPython @('-c','import django,waitress,argon2,PIL,onnxruntime,numpy')
        }
        [IO.File]::WriteAllText($ready, $lockHash)
    }
    Invoke-Checked $appPython @('-m','pip','check')
    $caddyDir = Join-Path $toolsDir ('caddy-' + $downloads.caddy.version)
    $caddy = Join-Path $caddyDir 'caddy.exe'
    $archive = Join-Path $toolsDir ('caddy-' + $downloads.caddy.version + '.zip')
    Get-VerifiedDownload $downloads.caddy $archive
    # Verified vendor archive only; expand to a dedicated versioned directory.
    if (-not (Test-Path -LiteralPath $caddy)) { Expand-Archive -LiteralPath $archive -DestinationPath $caddyDir -Force }
    Test-ArchiveExecutable $archive 'caddy.exe' $caddy
    Invoke-Checked $caddy @('version')
    $runtimeArgs = @('-m','scripts.windows_runtime','prepare','--profile',$InstallRoot)
    if ($TimeZone) { $runtimeArgs += @('--time-zone',$TimeZone) }
    if ($NonInteractive -or $Mode -in @('Account','Backup')) { $runtimeArgs += '--non-interactive' }
    Invoke-Checked $appPython $runtimeArgs
    if ($Mode -eq 'Prepare') { Write-Host '安装准备完成。普通双击启动时继续创建管理员及确认本机证书。'; return }
    $action = switch ($Mode) { 'Account' {'account'} 'Backup' {'backup'} 'Smoke' {'smoke'} default {'serve'} }
    $runArgs = @('-m','scripts.windows_runtime',$action,'--profile',$InstallRoot,'--caddy',$caddy)
    if ($Mode -eq 'Lan') {
        $addresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.AddressState -eq 'Preferred' -and $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and $_.PrefixLength -ge 16 -and $_.PrefixLength -le 30 })
        if (-not $addresses.Count) { throw '未发现可选的家庭私有 IPv4 地址；可使用本机模式。' }
        for ($i=0; $i -lt $addresses.Count; $i++) { Write-Host "[$($i+1)] $($addresses[$i].InterfaceAlias) $($addresses[$i].IPAddress)/$($addresses[$i].PrefixLength)" }
        $indexText = Read-Host '选择手机连接的可信家庭网络编号'
        $index = 0
        if (-not [int]::TryParse($indexText,[ref]$index) -or $index -lt 1 -or $index -gt $addresses.Count) { throw '网络选择无效。' }
        $network = $addresses[$index-1]
        $cidr = & $appPython -c 'import ipaddress,sys;print(ipaddress.ip_network(sys.argv[1],strict=False))' "$($network.IPAddress)/$($network.PrefixLength)"
        if ($LASTEXITCODE -ne 0) { throw '子网计算失败。' }
        $config = Get-Content -LiteralPath (Join-Path $InstallRoot 'profile.json') -Raw | ConvertFrom-Json
        Write-Host "将仅向 $($network.InterfaceAlias) 的 $cidr 开放 Caddy TCP $($config.web_port)，需要管理员 UAC 确认。"
        if ((Read-Host '确认这是可信家庭网络并允许开放？输入 YES') -cne 'YES') { throw '未开放网络。' }
        $lanFile = Join-Path $InstallRoot 'lan.json'
        $snapshot = & (Join-Path $PSScriptRoot 'windows_network.ps1') -Address $network.IPAddress | ConvertFrom-Json
        @{ ip=$network.IPAddress; cidr=$cidr; interface=$network.InterfaceAlias; port=$config.web_port; caddy=$caddy; rule=('ShiJinQiYong-' + $profileId); snapshot=$snapshot } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $lanFile -Encoding UTF8
        $firewallScript = Join-Path $PSScriptRoot 'windows_firewall.ps1'
        $firewallArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $firewallScript + '" -LanFile "' + $lanFile + '"'
        $elevated = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $firewallArgs -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        if ($elevated.ExitCode -ne 0) { throw '防火墙配置未完成；未启动局域网服务。' }
        $runArgs += @('--lan-ip',$network.IPAddress,'--cidr',$cidr)
    }
    Invoke-Checked $appPython $runArgs
} catch {
    Write-Host ('未完成：' + $_.Exception.Message) -ForegroundColor Red
    Write-Host '没有清空数据库或重置账号。可修复网络/安装条件后重新运行。帮助见 docs/WINDOWS.md。'
    exit 1
} finally {
    if ($locked -and $mutex) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
