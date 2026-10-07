# Windows：下载后双击部署食尽其用

## 适用范围

本入口面向 **Windows 10/11 x64、当前用户、本机 NTFS 磁盘**。首次安装需要访问 Python 官方 NuGet 包、PyPI 和 Caddy 官方 GitHub Release，约需 2 GB 可用空间。无需预装 Python、Git、Node、Docker 或 Caddy。企业策略禁止脚本、下载或可执行文件、Windows S 模式、32 位及 ARM64 不在本轮已验证范围；脚本明确停止，不绕过系统限制。

新电脑会创建自己的家庭数据库、账号及 CA。仓库只含程序和公开数据，下载源码不会取得原家庭库存。若只是访问原家庭，直接访问原主机经确认的 HTTPS 地址即可，不要另建家庭。

## 1. 下载和首次运行

1. 使用有仓库访问权限的 GitHub 账号，打开仓库，选择 **Code → Download ZIP**。
2. **先完整解压**到本机目录，例如 `C:\Apps\ShiJinQiYong`。不要在压缩包预览内直接运行。
3. 双击根目录 **Start-Windows.cmd**。通常使用普通 Windows 用户即可，不需“以管理员身份运行”。
4. 选择 **1 启动本机**，直接回车也可以。
5. 首次确认家庭 IANA 时区。窗口显示 Windows 当前时区供参考；例如确实使用中国标准时间时输入 `Asia/Shanghai`，不要把示例照搬到其他地区。
6. 等待自动下载与校验、准备 Python 3.13.16、创建独立虚拟环境、安装锁定依赖、准备 Caddy 2.11.7、迁移 SQLite、收集静态资源和安装随仓库附带的 YOLO。
7. 按提示设置家庭名称、管理员账号（最多 10 字符）和密码。密码输入**不显示字符**是正常情况，输入后按回车并再输入一次；至少 8 字符且经过 Django 强度校验。**没有默认密码**。
8. 服务完成严格 HTTPS 自检后显示本家庭公开根证书的 SHA-256 指纹、文件路径，并询问是否信任。确认这是自己刚部署的家庭应用后输入 `y`，仅加入当前 Windows 用户的根信任；不需要让所有系统用户信任。选择不信任仍保留数据，但不要越过浏览器证书警告输入密码。
9. 同意信任后自动打开浏览器，使用刚创建的账号登录。通常是 `https://localhost:8443/`，如首次端口被占用，脚本自动选择并保存其他空闲端口，**以窗口显示的网址为准**。

以后双击同一入口，回车即可启动。不会重新创建管理员、轮换密钥或重置库存。窗口需要保持开启，按 **Ctrl+C** 停止；启动器使用 Windows Job 管理本轮子进程，退出时一起停止 Waitress/Caddy。没有安装后台常驻服务或开机任务，电脑关机后应用不可访问。

若首次 VC++ DLL 检查失败，脚本从 Microsoft 官方地址下载并验证签名，再安装 VC++ x64 运行库；系统可能要求 UAC，需要操作者决定是否同意。此操作不会关闭杀毒软件或防火墙。

## 2. 注册、密码和账号维护

- **新家庭第一个账号：**由运行脚本的本机控制台创建管理员，服务启动前完成，远程网页不能抢先注册管理员。
- **其他家庭成员：**管理员登录 → 家庭设置 → 生成家庭邀请码 → 私下交给允许加入的人；对方在封面点击“注册”。邀请码 24 小时内有效、只能使用一次；管理员可撤销未使用的邀请。新注册账号只有普通成员权限。
- **修改自己的密码：**家庭设置 → 修改我的密码；输入原密码和两次新密码。本次登录保留，其他设备的旧登录失效。
- **忘记密码或登录锁定：**先在运行窗口 Ctrl+C 停止，再双击启动脚本选择 **3 账号维护**，按菜单重设密码、解除账号锁定、创建管理员或启用/禁用账号。密码不放在命令行或日志中。本机恢复是主机持有者权限，没有公开网页重置密码入口。
- **旧版安装：**继续使用原 `scripts/manage_prod.ps1 manage_member ...` 管理原家庭；新入口维护的是新私有目录，不能把两个家庭账号混为一谈。

登录、退出、改密、邀请及注册继续受 Django 会话、CSRF、密码哈希和成员角色保护；不引入共享口令或 JWT。密码眼睛、配色和现有库存流程保持。

## 3. 手机与同一家庭 Wi-Fi 访问

1. 停止本机模式，双击入口选择 **2 启动可信家庭局域网**。
2. 从窗口列出的实际网卡与 IPv4 中选手机所在家庭 Wi-Fi。确认网段可信后输入 `YES`。
3. 允许本次防火墙配置的 UAC 提示。规则仅放行所选网卡、电脑 IPv4、来源子网、Caddy 程序和显示的 TCP HTTPS 端口；不开放后端端口、不配置路由器、不关闭防火墙。
4. 窗口显示 `https://<此电脑的IPv4>:<端口>/`。电脑仍可用显示的 localhost 地址。
5. 手机需通过可信渠道取得 **此电脑生成的公开 root.crt**，对照窗口的 SHA-256 指纹，在手机系统中自行安装并信任 CA。只传公开证书，不传 `root.key`、`intermediate.key` 或整个 caddy 目录。
6. 手机同 Wi-Fi 打开 `/health/`，**无证书警告且显示 `{"status":"ok"}`**后再登录。证书导入、手机浏览器信任及路由器设备隔离无法由 Windows 脚本替手机完成。

每次局域网启动都要重新选择并确认当前网络；脚本监测运行期间的 IPv4、网卡与网络名称变化，发现改变或无法检查会停止服务（约 5 秒检查间隔）。该检测不替代可信网络判断，名称相同不证明网络可信。新 Wi-Fi 不会自动获准。普通启动默认只监听本机。

防火墙规则名为 `ShiJinQiYong-<此实例标识>`，仅本启动器的规则可能更新，不修改原主机服务的规则。停用后可在管理员 PowerShell 用 `Get-NetFirewallRule -Name 'ShiJinQiYong-*'` 核对并移除对应实例规则；不要批量删除其他家庭的规则。

## 4. 数据位置、更新和备份

默认目录是 `%LOCALAPPDATA%\ShiJinQiYong`（当前 Windows 用户独立）：

| 内容 | 位置 |
|---|---|
| 私有配置、随机密钥与已选端口 | `profile.json` |
| SQLite 与家庭上传附件 | `data/app.sqlite3`、`data/recipe_media/` |
| 完整数据库+附件备份 | `data/backups/household-.../` |
| Caddy 私钥、证书和持续 CA | `caddy/` |
| 可公开分发的根证书 | `caddy/pki/authorities/local/root.crt` |
| 指纹静态文件 | `static/` |
| 独立 Python、Caddy、下载缓存 | `tools/` |
| 按依赖锁区分的虚拟环境 | `venvs/` |
| 本机启动诊断 | `server.log`（每次启动重新写入，不应公开上传） |

目录 ACL 仅允许当前用户与 SYSTEM，拒绝共享盘、OneDrive、链接目录等不适合 SQLite 的位置。其他用户的显式访问权限会使安装停止。通过 MSIX 宿主运行时 Windows 可能重定向 LOCALAPPDATA；以实际控制台/运行配置显示的路径为准。

**更新：**Ctrl+C 停止 → 下载并解压新源码 → 双击新目录的 Start-Windows.cmd。相同 Windows 用户仍使用同一私有目录；依赖锁改变时创建新环境，保留旧环境。启动前先校验依赖，检测到代码/依赖版本改变时备份已有数据库及被引用附件，然后迁移和收集静态资源；相同代码重复启动不反复复制附件。任何步骤失败就停止，不自动回退覆盖新数据。没有迁移变更时显示无待执行项。

**主动备份：**停止运行后选择菜单 **4 备份**，把生成的整个 `household-...` 目录私下复制到受保护的异设备。不能只取 SQLite 丢掉图片/视频。备份不含运行密钥及 CA；若希望同一设备更换源码不影响会话/证书，保留原私有目录。迁移到另一主机时应新建 CA 并重新建立设备信任，不把 CA 私钥上传 GitHub。

**恢复/回退：**先停止所有写入并另存当前私有目录，不直接覆盖。将完整备份复制到新的受保护测试目录，按 [HANDOFF.md](HANDOFF.md) 的 SQLite 完整性、外键、附件散列和清除旧会话流程核验；确认后由主机持有者切换数据。代码回退须核对数据库迁移兼容性。本轮无新表迁移，但后续版本不能假定旧代码理解新数据。旧依赖环境保留，禁止自动删库重装。

## 5. 常见问题

| 现象 | 处理 |
|---|---|
| 双击后窗口直接关闭 | 完整解压，再从 PowerShell 运行入口查看错误；不要改全局执行策略。cmd 只对本次 PowerShell 进程设置执行策略，组织组策略仍有效。 |
| 下载超时/被阻断 | 检查到 NuGet、PyPI、GitHub 的正常 HTTPS 访问；重跑会复用已校验缓存，残缺 `.partial` 会重新下载。不要使用 `--trusted-host` 或关闭 TLS。 |
| SHA/签名不符 | 停止，不运行文件；核对来源/版本后移走报错的缓存再重试。版本固定，维护者核验后才更新 manifest。 |
| 显示实例正在运行 | 返回原窗口使用已有网址，或 Ctrl+C 停止后再启动；不要终止其他 Python 服务。 |
| 已保存端口被占用 | 脚本停止并给端口号；先找占用程序。首次会选空闲端口，后续不会悄悄更换已有网址。 |
| 手机证书警告 | 手机未信任当前家庭 CA，不能点击继续后登录；按第 3 节处理。 |
| 新电脑登录不了旧账号 | 这是独立空家庭。访问原主机，或私下迁移备份；不自动同步数据库。 |
| 检测到旧 `data/runtime.env` | 原服务不受影响。只有明确输入 `NEW` 才创建另一独立家庭；不要误以为迁移完成。 |
| Python/VC++ 被系统策略阻止 | 根据组织规定处理，脚本不会关闭防护或绕过策略。 |
| 照片识别不可用 | 核对仓库含完整 `model_assets` 及模型校验，查看本机错误；可手工录入，不回退在线视觉模型。 |

## 6. 已安装原主机仍使用旧服务

本轮不接管或改动旧 `ShiJinQiYongCaddy` 服务、`ShiJinQiYong-Waitress` 任务或 `data/runtime.env`。

```powershell
Get-Service ShiJinQiYongCaddy
Get-ScheduledTask -TaskName ShiJinQiYong-Waitress
Start-Service ShiJinQiYongCaddy
Start-ScheduledTask -TaskName ShiJinQiYong-Waitress
```

上面 Caddy 命令需要管理员；网络必须仍是原确认的网络。源码更新按原 `stop_waitress_for_backup.ps1` → `manage_prod.ps1 backup_household` → 依赖/迁移/collectstatic → 重启流程。旧配置初始化脚本现要求显式 `-LanIp <本机可信IPv4> -TimeZone <家庭时区>`，不再带原电脑地址；新电脑推荐双击入口。

## 7. 可复现的维护检查

只在独立合成目录使用以下非交互参数，不用于冒充账号/证书人工验收：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows_setup.ps1 -Mode Prepare -InstallRoot "$env:LOCALAPPDATA\ShiJinQiYong-Test" -TimeZone Asia/Shanghai -NonInteractive
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows_setup.ps1 -Mode Smoke -InstallRoot "$env:LOCALAPPDATA\ShiJinQiYong-Test" -NonInteractive
```

Prepare 不创建管理员；Smoke 使用独立 Caddy CA 严格验证健康页后停止，不导入系统证书，不开放 LAN。自动化账号测试和本机实际运行记录见 [PROGRESS.md](PROGRESS.md)。真实另一台空白 Windows、UAC 防火墙操作、断网/重启及手机信任需分别记录，不据本机检查声称“任意电脑全部通过”。

资料：[Python 官方 NuGet 发行说明](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages)、[CPython 3.13.16 包](https://www.nuget.org/packages/python/3.13.16)、[Caddy 2.11.7](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)、[Caddy 内部 HTTPS 与信任](https://caddyserver.com/docs/automatic-https)。
