# macOS：在自己的 Mac 上运行食尽其用

这份说明用于**新 Mac 的独立安装**。GitHub 只保存程序、公开菜谱与文档；每台 Mac 首次运行会建立自己的空 SQLite 和管理员账号，**不会自动看到原电脑的家庭库存或采购记录**。想查看同一份家庭记录，应在同一可信局域网访问原电脑的 HTTPS 地址，并先解决客户端证书信任；如确需迁移数据，应私下转移经过保护的数据库与附件备份，不能上传 GitHub。

## 1. 下载与准备

让仓库所有者先在 GitHub 授予你的账号读取权限。在 Mac 终端安装 Git、Python 3.12 与 Caddy。已使用 Homebrew 的 Mac 可以运行：

```bash
brew install git python@3.12 caddy
git clone https://github.com/yangxufe/SHIJINQIYONG.git
cd SHIJINQIYONG
python3.12 --version
caddy version
```

请把项目放在本机磁盘目录，避免把运行中的 SQLite 放在 iCloud、OneDrive、Dropbox 或网络共享目录。Homebrew 的 Caddy 安装方式见[官方安装页](https://caddyserver.com/docs/install)。下面不要求 Node、云数据库或另一个 Web 框架。

先确认 Mac 和访问设备在**同一个你信任的家庭 Wi-Fi**。查找 Wi-Fi 对应的设备名：

```bash
networksetup -listallhardwareports
ipconfig getifaddr en0
ipconfig getoption en0 subnet_mask
```

上面的 `en0` 只是例子，须替换成 `networksetup` 显示的 Wi-Fi 设备名。假设地址为 `192.168.1.50`、掩码为 `255.255.255.0`，网络 CIDR 就是 `192.168.1.0/24`；不要照抄这个示例地址。也可用本机 Python 计算：

```bash
python3.12 -c 'import ipaddress,sys; print(ipaddress.IPv4Network((sys.argv[1],sys.argv[2]), strict=False))' "$(ipconfig getifaddr en0)" "$(ipconfig getoption en0 subnet_mask)"
```

## 2. 首次安装

将下面的地址、CIDR 和 IANA 时区替换为**实际值**，在项目根目录执行：

```bash
bash scripts/setup_macos.sh 192.168.1.50 192.168.1.0/24 Asia/Shanghai
.venv/bin/python scripts/macos_runtime.py manage manage_member create myname --role admin
```

脚本创建 `.venv`、私有 `data/runtime.env`、随机 Django 密钥、空 SQLite、迁移与静态文件；已有运行配置不会被覆盖。账号密码在终端交互输入，不出现在命令历史。时区例子为 `Asia/Shanghai`；按实际家庭时区替换，留空则默认 UTC。安装前需要 Caddy 和 Python 3.12 已在 PATH 中。设置脚本不会安装根证书或打开路由器端口。

如需在这台 Mac 上自行运行回归测试，完成首次安装后执行 `mkdir -p work && .venv/bin/python manage.py test tests --settings=config.settings.test`。测试数据只进入独立测试库，不应写入家庭数据库。

若换了已确认的家庭 Wi-Fi，先停止 Caddy，核对新 IP 与子网，再运行：

```bash
.venv/bin/python scripts/macos_setup.py 192.168.2.50 192.168.2.0/24 --update-ip
.venv/bin/python scripts/macos_runtime.py manage check --deploy
```

更新只改 IP、子网、Host 与 CSRF Origin，不重置账号、密钥、数据库或家庭附件。没有人工确认新网络时不要执行。Mac 端代理还按指定 CIDR 拒绝其他来源，并在启动时检查指定 IP 确实在本机网卡上。

## 3. 启动服务并打开页面

在项目根目录打开**两个终端窗口**。窗口 A：

```bash
.venv/bin/python scripts/macos_runtime.py waitress
```

窗口 B：

```bash
.venv/bin/python scripts/macos_runtime.py caddy
```

Waitress 只监听 `127.0.0.1:8000`；Caddy 只绑定已确认的 Mac 局域网 IP，使用 HTTPS `8443`，并只允许所填家庭子网的请求。两个窗口关闭后服务即停止；没有在 Mac 上安装常驻开机服务。不要把 Waitress 的 `8000` 暴露给局域网，也不要配置公网端口转发。

先在 Mac 终端核对健康页。Caddy 首次启动后，会在**私有** `data/caddy/pki/authorities/local/` 生成该 Mac 独有的 CA：

```bash
shasum -a 256 data/caddy/pki/authorities/local/root.crt
curl --cacert data/caddy/pki/authorities/local/root.crt https://192.168.1.50:8443/health/
```

第二条命令应返回 `ok`；请把示例 IP 换成你自己的。不要用 `curl -k` 跳过校验。浏览器与手机也必须**各自信任这台 Mac 的公开根证书**，否则会出现证书警告。Mac 管理员可在核对指纹后按 [Caddy 官方说明](https://caddyserver.com/docs/running)把 `root.crt` 安装到系统信任库；只分享 `root.crt` 给确实要访问的家庭设备，绝不分享同目录的私钥。证书警告仍在时不要输入账号密码。

同一 Wi-Fi 的手机或另一台电脑，在各自信任该 Mac 的根 CA 后打开：

```text
https://<Mac的当前家庭IPv4>:8443/
```

如果无法连接，检查两台设备是否真在同一子网、访客 Wi-Fi 是否隔离设备、Mac 系统防火墙是否允许 Caddy 入站、两个终端是否仍在运行，以及地址是否已变化。不能通过关闭 Django 安全设置或把 Waitress 暴露到局域网来排障。

## 功能与数据边界

- 本机拍照识别依赖另装并运行的本地 Ollama 与已下载视觉模型；没有它时手工录入可用。菜谱外部生成默认关闭，既不需要在线 AI 密钥，也不应把密钥提交到 GitHub。
- Caddy 的 Windows 配置 `config/Caddyfile` 含原电脑地址；Mac 只使用 `config/Caddyfile.macos`。每台机器生成自己的 `data/runtime.env` 和 CA，不复用别人的密钥。
- 要备份本机家庭记录，先停止 Waitress，再以 `.venv/bin/python scripts/macos_runtime.py manage backup_household` 备份数据库和附件，并把整个私有备份目录另存到受保护的位置。源码仓库不承担数据备份。
- 本教程的脚本与 Caddy 配置在 Windows 开发机经过语法和自动化检查；**没有在真实 Mac 或另一台手机上执行安装、证书信任和访问验收**。遇到系统弹窗或浏览器证书问题请以实际设备结果为准。
