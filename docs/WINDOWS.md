# Windows：启动食尽其用

先选使用方式：

- **访问原家庭数据：**Windows 电脑与原主机在同一个已确认的家庭 Wi-Fi 时，直接用浏览器打开原主机的 HTTPS 地址；不需要克隆仓库或另建数据库。客户端必须信任**原主机**的家庭根证书，无证书警告后才能登录。
- **在另一台 Windows 电脑独立运行：**按下文首次安装。GitHub 只有程序和公开参考数据，新安装会创建**空的本机 SQLite、自己的账号与自己的 Caddy 根证书**，不会自动得到原家庭库存。需要迁移家庭数据时，私下转移受保护的数据库与附件备份，不要上传 GitHub。

不要把运行目录放在 OneDrive、Dropbox、网盘或网络共享盘中。以下命令在 **PowerShell** 中执行；示例 IP、网卡名、时区都必须替换为实际值。不要在不可信 Wi-Fi 上开放端口，也不要设置路由器端口转发。

## A. 已安装的原 Windows 主机：日常启动

在项目根目录打开 PowerShell，先确认电脑仍连接此前获准的家庭 Wi-Fi，且当前 IPv4 与私有 `data/runtime.env`、Caddy 和防火墙规则一致：

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength,InterfaceAlias
Get-Service ShiJinQiYongCaddy
Get-ScheduledTask -TaskName ShiJinQiYong-Waitress
Get-NetTCPConnection -State Listen -LocalPort 8000,8443 -ErrorAction SilentlyContinue
```

本项目在原主机已有 `ShiJinQiYongCaddy` 服务与 `ShiJinQiYong-Waitress` 登录任务。服务或任务停止时，用管理员 PowerShell 启动 Caddy，用运行该任务的 Windows 账号启动 Waitress：

```powershell
Start-Service ShiJinQiYongCaddy
Start-ScheduledTask -TaskName ShiJinQiYong-Waitress
```

再次检查：Waitress 只能监听 `127.0.0.1:8000`，Caddy 应监听已确认的家庭 IPv4 的 `8443`。在浏览器打开 `https://<当前已配置的家庭IPv4>:8443/health/`，应见 `{"status": "ok"}`。地址变化时，**先确认新网络可信**，再同步 Django Host/CSRF、Caddy 监听地址及防火墙范围；不能仅把网址里的数字改掉。手机仍出现证书警告时不要输入账号密码。原主机的现行状态与证书人工步骤见 [HANDOFF.md](HANDOFF.md)。

## B. 在另一台 Windows 电脑首次安装

### 1. 准备程序和网络信息

从官方渠道安装 [Git](https://git-scm.com/download/win)、[Python 3.12 的当前维护补丁](https://www.python.org/downloads/windows/)和 [Caddy](https://caddyserver.com/docs/install)，让 `git`、`py -3.12`、`caddy` 在 PowerShell 中可用。安装后确认：

```powershell
git --version
py -3.12 --version
caddy version
```

在新电脑上确认你信任的家庭 Wi-Fi、IPv4、前缀长度和网卡名；不要照抄原主机的 `192.168.110.146`：

```powershell
netsh wlan show interfaces
Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength,InterfaceAlias
```

下文以 `$LanIp = '192.168.1.50'`、`$Prefix = 24`、`$WifiAlias = 'Wi-Fi'` 为**示例**。先确认 IP 确实属于所选网卡，再计算子网：

```powershell
$LanIp = '192.168.1.50'
$Prefix = 24
$WifiAlias = 'Wi-Fi'
$Cidr = py -3.12 -c "import ipaddress,sys; print(ipaddress.ip_network(f'{sys.argv[1]}/{sys.argv[2]}', strict=False))" $LanIp $Prefix
$Cidr
```

如果 `8443` 或 `8000` 已被别的程序占用，先找出程序；不要与原有实例并行启动，也不要只改 Caddy 端口而漏改 Django 的 CSRF Origin 与防火墙规则。

### 2. 下载、安装依赖、创建本机配置

先确保 GitHub 账号有仓库读取权限。选择本机非同步目录，例如：

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\Projects" -Force | Out-Null
Set-Location "$env:USERPROFILE\Projects"
git clone https://github.com/yangxufe/SHIJINQIYONG.git
Set-Location .\SHIJINQIYONG
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock
& .\.venv\Scripts\python.exe -m pip check
```

先检查 `data/runtime.env` **不存在**，再运行现有初始化脚本。它只生成一次随机密钥，不会覆盖已有配置：

```powershell
Test-Path .\data\runtime.env
& .\scripts\initialize_runtime.ps1
```

当前初始化脚本带有**原主机 IP 和静态目录默认值**。在首次迁移数据库或启动服务前，打开生成的私有文件 `notepad .\data\runtime.env`，只把以下四行改成**这台新电脑的真实值**；`SHIJIN_SECRET_KEY` 与 `SHIJIN_DATA_DIR` 保留原样，不要把文件内容贴到聊天、日志或 GitHub：

```text
SHIJIN_ALLOWED_HOSTS=192.168.1.50
SHIJIN_CSRF_TRUSTED_ORIGINS=https://192.168.1.50:8443
SHIJIN_TIME_ZONE=Asia/Shanghai
SHIJIN_STATIC_ROOT=C:/Users/<你的Windows用户名>/Projects/SHIJINQIYONG/collected_static
```

`Asia/Shanghai` 只是示例，按家庭实际 IANA 时区填写；静态目录必须是实际的本机绝对路径，和私有 `data/` 分开。先确认 `SHIJIN_ALLOWED_HOSTS` 与 `SHIJIN_CSRF_TRUSTED_ORIGINS` 已不再是原主机 IP。把新建的私有 `data/` 目录限制为当前 Windows 用户及 SYSTEM 可访问，并在其中创建 Caddy 私有存储：

```powershell
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$PrivateDir = (Resolve-Path .\data).Path
& icacls.exe $PrivateDir /inheritance:r /grant:r "${Identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F'
& icacls.exe (Join-Path $PrivateDir 'runtime.env') /inheritance:r /grant:r "${Identity}:F" 'SYSTEM:F'
New-Item -ItemType Directory -Path .\data\caddy -Force | Out-Null
```

如果权限命令失败，先停止安装并检查目录“属性 → 安全”；不要在权限不明的共享目录保存密钥或数据库。接着在项目根目录执行：

```powershell
& .\scripts\manage_prod.ps1 check --deploy
& .\scripts\manage_prod.ps1 migrate --noinput
& .\scripts\manage_prod.ps1 collectstatic --noinput
& .\scripts\manage_prod.ps1 manage_member create myname --role admin
```

把 `myname` 改为自己的账号名。密码会交互输入、不回显；没有默认账号。`check --deploy` 可能仍显示已记录的 IP 访问 HSTS 提示；其他错误要先修复。可选的测试在新建 `work/` 后运行：`New-Item -ItemType Directory work -Force | Out-Null; & .\.venv\Scripts\python.exe manage.py test tests --settings=config.settings.test`。测试使用隔离数据库，不应写入家庭库。

### 3. 启动 Waitress 与 Caddy

打开两个新的 PowerShell 窗口，都进入项目根目录。**窗口 A** 运行：

```powershell
& .\scripts\start_waitress.ps1
```

它只监听 `127.0.0.1:8000`。**窗口 B** 不加载 Django 的密钥，只把已经确认的网络和本机目录传给 Caddy：

```powershell
$LanIp = '192.168.1.50'        # 改成新电脑当前的可信家庭 IPv4
$Cidr = '192.168.1.0/24'       # 改成上一步计算出的子网
Get-ChildItem Env:SHIJIN_* -ErrorAction SilentlyContinue | Remove-Item
$env:SHIJIN_LAN_IP = $LanIp
$env:SHIJIN_ALLOWED_CIDR = $Cidr
$env:SHIJIN_STATIC_ROOT = (Resolve-Path .\collected_static).Path.Replace('\', '/')
$env:SHIJIN_CADDY_STORAGE = (Resolve-Path .\data\caddy).Path.Replace('\', '/')
caddy adapt --config .\config\Caddyfile.windows --adapter caddyfile --validate | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Caddy 配置检查失败，服务未启动。' }
caddy run --config .\config\Caddyfile.windows --adapter caddyfile
```

新 Windows 配置绑定指定 IPv4 的 HTTPS `8443`，Caddy 再按指定家庭 CIDR 拒绝其他来源；大文件上传只在菜谱附件路径放行。两个窗口关闭后服务停止。这里没有创建常驻 Windows 服务，照片识别所需的本机 Ollama 也不是基础功能的启动前提。

### 4. 只对已确认的家庭网络放行端口

手机要访问时，在**管理员 PowerShell** 中重新填写同一 IP、CIDR 和网卡名，并确认 `caddy.exe` 的真实路径。以下规则仅针对这台电脑的 Caddy 程序、网卡、本地地址、来源子网和 TCP 8443；已有同名规则时先核对，不重复创建：

```powershell
$LanIp = '192.168.1.50'
$Cidr = '192.168.1.0/24'
$WifiAlias = 'Wi-Fi'
$CaddyExe = (Get-Command caddy.exe).Source
if (Get-NetFirewallRule -DisplayName 'ShiJinQiYong-Manual-8443' -ErrorAction SilentlyContinue) {
    throw '同名防火墙规则已存在，请先核对。'
}
New-NetFirewallRule -DisplayName 'ShiJinQiYong-Manual-8443' -Direction Inbound -Action Allow `
    -Program $CaddyExe -Protocol TCP -LocalPort 8443 -LocalAddress $LanIp `
    -RemoteAddress $Cidr -InterfaceAlias $WifiAlias -Profile Any
```

这一步需要管理员权限。新网络未经确认时不要沿用旧规则开放应用；网络或 IP 改变时先停止 Caddy，再同步运行配置、Caddy 的两个网络变量和防火墙规则。

### 5. 校验证书后访问

Caddy 首次启动会在这台电脑的私有 `data/caddy/pki/authorities/local/` 生成新的根证书。先在电脑上**严格校验证书**并检查健康页；下面使用 Python 读取公开 `root.crt`，没有关闭 TLS 校验：

```powershell
Get-FileHash .\data\caddy\pki\authorities\local\root.crt -Algorithm SHA256
& .\.venv\Scripts\python.exe -c "import ssl,sys,urllib.request; ctx=ssl.create_default_context(cafile=sys.argv[1]); print(urllib.request.urlopen(sys.argv[2],context=ctx,timeout=5).read().decode())" .\data\caddy\pki\authorities\local\root.crt "https://${LanIp}:8443/health/"
```

应返回 `{"status": "ok"}`。浏览器和手机还需分别信任**这台新电脑**的公开 `root.crt`，核对复制前后的 SHA-256；不要复制或上传同目录私钥。Windows 当前用户在核对证书后可自行决定是否运行 `certutil -user -addstore Root .\data\caddy\pki\authorities\local\root.crt`，Android 按系统设置中的“安装 CA 证书”导入。Caddy 的 [官方运行说明](https://caddyserver.com/docs/running)也说明了其他设备须分别信任内部 CA。若仍有证书警告，不要点击继续后输入密码。

手机与电脑位于同一已确认的家庭 Wi-Fi、证书无警告时，打开 `https://<新电脑当前家庭IPv4>:8443/`。若打不开，先检查两个服务窗口、`Get-NetTCPConnection -State Listen -LocalPort 8000,8443`、防火墙规则、手机实际网段和 Wi-Fi 是否启用了设备隔离。502 通常需要检查 Waitress；静态文件 404 要核对 `SHIJIN_STATIC_ROOT` 与 `collectstatic`；登录后 CSRF 错误要核对 Host/Origin 与浏览器实际网址。不要用 `DEBUG=True`、`ALLOWED_HOSTS=*`、关闭 CSRF 或直接开放 `8000` 来排障。

## 备份、更新与已知边界

关掉窗口 A 停止新电脑上的 Waitress 写入，再运行 `& .\scripts\manage_prod.ps1 backup_household`；整个私有备份目录包含 SQLite 与已引用附件，必须作为一组另存到受保护的位置。更新源码前先备份，再 `git pull --ff-only`、安装锁定依赖、执行迁移与 `collectstatic`，最后重启两个窗口。不要把 `data/`、证书私钥、运行配置、密码或 Cookie 推到仓库。

原 Windows 主机的日常启动与健康探测有现有运行记录；**本篇新电脑首次安装流程未在另一台 Windows 或 Android 上端到端执行**。当前原主机的 Android 证书信任仍有未完成项，不能据电脑端健康页声称手机已能安全登录。Python 虚拟环境、Caddy Windows 运行及防火墙参数分别参见 [Python 官方文档](https://docs.python.org/3.12/library/venv.html)、[Caddy 官方文档](https://caddyserver.com/docs/running)和 [Microsoft 防火墙命令文档](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)。
