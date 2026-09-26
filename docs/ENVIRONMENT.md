# 阶段 01 环境记录

核验日期：2026-09-25。以下均为本机实际检测；手机结果单列为用户提供的现场反馈。

| 项目 | 实际情况 |
|---|---|
| 操作系统 | Windows 11 Pro for Workstations，64 位，build 26200 |
| 执行身份 | 当前交互会话非提升权限；配置服务和防火墙时通过 Windows 管理员提升 |
| Python | 3.10.20，隔离环境 `.venv` |
| Django | 5.2.17，5.2 LTS 分支截至实施日期的补丁版本 |
| Waitress | 3.0.2，4 线程，`127.0.0.1:8000` |
| Caddy | 2.11.4，服务身份 `NT AUTHORITY\LocalService`，手动启动 |
| SQLite | Python 实际加载的 3.53.2；当前数据库 `journal_mode=delete` |
| 时区 | 系统检测为 `China Standard Time`；运行配置显式设 `Asia/Shanghai` |
| Git | 当前目录不是 Git 仓库 |

Python 依赖在虚拟环境中安装；当前机器的 pip 索引配置指向清华镜像。直接核对了官方 Django 5.2 发布信息、Waitress 发布记录、Caddy 发布资产和 SQLite WAL 文档，并在 `requirements.lock` 精确锁定当前依赖。`pip check` 退出码 0。Caddy 官方 ZIP 的发布 SHA-512 校验值与 GitHub 发布资产 SHA-256 摘要均已核对。

SQLite 官方说明 WAL-reset 问题从 3.51.3 起修复；3.53.2 满足版本底线。阶段 01 仍保留默认 DELETE 回滚日志模式，待阶段 03 完成真实文件数据库并发测试后再决定是否启用 WAL。数据库文件位于本机项目的 `data/`，不在 OneDrive 规格包或静态目录中。

## 网络与证书

- WLAN 实测 `192.168.1.127/24`，Windows 当前网络配置为 Public。用户确认这是供手机测试的家庭 Wi-Fi。
- 按用户明确要求，HTTPS 使用 `8443`，因为 `80/443` 已由 Steam++.Accelerator 占用；没有修改该程序。
- Caddy 只绑定 `192.168.1.127:8443`；Windows 入站规则限定 Caddy 程序、WLAN、本机该地址与 `192.168.1.0/24` 来源。Waitress 只监听 IPv4 loopback 的 `8000`，未设 LAN 入站规则。
- 监听检查仅发现上述两个 IPv4 地址上的 8000/8443，没有这两个端口的 IPv6 监听。需要撤销局域网放行时，在管理员 PowerShell 运行 `Disable-NetFirewallRule -Name 'ShiJinQiYong-Caddy-HTTPS-8443-WLAN'`；恢复时运行相应的 `Enable-NetFirewallRule`。不关闭整个防火墙。
- Caddy 服务程序位于 `C:\Program Files\ShiJinQiYong\Caddy`，配置与持久 CA 数据位于 `C:\ProgramData\ShiJinQiYong`；CA 目录只授予 LocalService、SYSTEM 和管理员访问。公开根证书单独导出到 `outputs/`，私钥未导出。
- 公开根证书 DER SHA-256 指纹：`5A:49:BD:03:CC:C8:2B:8F:C3:55:77:23:3A:F2:FA:27:1B:FE:F6:D9:2A:C7:6F:04:12:71:09:75:74:D6:EE:FF`。本机使用该证书验证实际 HTTPS 请求，未关闭证书校验。
- Caddy 禁用 HTTP 自动跳转端口和管理 API，仅将应用请求代理到 `127.0.0.1:8000`；静态资源仅从 `C:\ProgramData\ShiJinQiYong\static` 提供。未操作路由器；现有公网映射状态未核验。

生产设置要求随机密钥、显式 Host 和 HTTPS Origin，`DEBUG=False`，安全 Cookie、CSRF、CSP 和动态响应 `no-store`。`check --deploy` 的唯一警告是 HSTS 未启用；当前按局域网 IP 访问，架构约定不把 HSTS 当作 IP 的可靠保护。若未来改用受信域名，应重新评估并配置。

## 仍需现场核对

阶段 01 结束时，用户已报告手机能访问此前的 Caddy 连通性测试页。后续现场反馈见下节。网络地址、网段或 Windows 网络配置变化后，需要复核 Caddy、Django 和防火墙配置。

## 阶段 02 补充

- 用户已反馈手机可连接；反馈未明确新登录页是否无证书警告，以及另一设备是否无法直连 `8000`，这两项仍需现场核对。
- 新增 `django-axes==8.3.1` 数据库节流模式。5 次失败后账号或实际来源 IP 被锁定 15 分钟；可用本机 `manage_member unlock` 按账号或 IP 解除。Waitress 只信任 loopback Caddy；应用仅在该跳读取被 Caddy 覆盖的单个 `X-Forwarded-For` 值。
- 阶段 02 前使用 Python sqlite3 在线备份 API 创建私有 `data/backups/stage01-before-stage02.sqlite3`，备份与迁移后数据库的 `PRAGMA integrity_check` 均为 `ok`。数据目录与文件的 ACL 已限定当前用户、SYSTEM、Administrators。曾在收紧 ACL 的首次操作中意外移除数据库文件访问规则，立即恢复后才执行迁移；操作和验证记录见 `PROGRESS.md`。
- 生产库目前 0 个账号、0 个批次、0 个购物项；演示账号只在独立测试库创建。静态 CSS 已重新收集，Waitress 已重启；Caddy 服务和 8443 防火墙规则保持运行。

资料：[Django 5.2 发布记录](https://docs.djangoproject.com/en/5.2/releases/)、[Waitress 文档](https://docs.pylonsproject.org/projects/waitress/en/stable/)、[Caddy 发布页](https://github.com/caddyserver/caddy/releases/tag/v2.11.4)、[SQLite WAL](https://www.sqlite.org/wal.html)。

## 阶段 03 补充

- 用户在阶段 03 开始前反馈手机测试成功；这一反馈没有包含新库存页面的录入和扣减验收。阶段 03 结束时，Caddy 仍通过 `192.168.1.127:8443` 提供可信 HTTPS，Waitress 仍只监听 `127.0.0.1:8000`。本机使用公开根证书验证了 HTTPS 请求，没有跳过证书验证。
- 生产库迁移前用 Python `sqlite3.backup` 建立私有 `data/backups/stage02-before-stage03.sqlite3`；备份完整性为 `ok`。迁移后生产库 `PRAGMA integrity_check=ok`，`journal_mode=delete`。当前 2 个成员账号、0 个批次、0 个业务动作、0 条库存流水；合成用例只写独立测试库。
- 库存测试使用磁盘上的 Django 测试 SQLite 文件，不使用内存库。并发用不同连接与同时起跑屏障；锁占用用独立 SQLite 连接。数据库 `transaction_mode=IMMEDIATE`、约 2 秒有界锁等待；当前没有启用 WAL。
- 两个独立 Python 进程在独立合成文件库先写后读，验证提交后数量、动作和流水仍在。此检查不是 Windows 服务或主机重启验收；Waitress 当前仍依赖交互会话。
- 库存前端 JavaScript 和 CSS 由本机 Caddy 指纹静态路径提供；不需要 Node 运行时。浏览器网络失败时保留本页原请求编号供重试，页面刷新后不会离线缓存待写动作。
- 本机阶段 03 HTTPS 复核发现已部署 Caddy 对指纹静态文件仍发 `Cache-Control: no-store`。仓库 `config/Caddyfile` 已改为只让 12 位哈希命名的静态文件长期缓存、其他静态文件继续 `no-store`；语法转换退出码 0。现运行的管理员保护配置尚未替换，实际缓存头仍是 `no-store`，待管理员应用和再次核验。非提升权限下的完整配置验证因无法读取私有 CA 根证书而退出码 1，不能据此声称生产配置已更新。

## 阶段 04 补充

- 用户在阶段 04 开始时反馈阶段 03 已测试；未提供逐项手机结果或性能数字。阶段 04 的手机首页与搜索尚待用户在手机上验收，本机浏览器检查不能替代。
- 迁移前通过 Python `sqlite3.backup` 创建私有 `data/backups/stage03-before-stage04.sqlite3`，备份 `integrity_check=ok`。已应用库存 0003 手动优先字段迁移。迁移后生产库 `integrity_check=ok`、`journal_mode=delete`；只读计数为 2 个成员账号、0 个批次。没有将演示食材写入生产库。
- 阶段 04 浏览器只访问绑定 `127.0.0.1:8765` 的独立开发进程和 `work/stage04-browser-data/app.sqlite3` 合成库，测试后已停止进程。合成库包含专用测试账号与批次，不在交付 ZIP 内。真实浏览器视口检查：360、390、430 CSS 像素时页面 `scrollWidth` 未超过 `innerWidth`；底部四入口实测高 48 CSS 像素，批次操作按钮实测高 44 CSS 像素。
- 实际浏览器截图 `outputs/STAGE04_TODAY_390.png` 与 `outputs/STAGE04_INVENTORY_390.png` 来自上述合成库，不代表真实家庭记录或真实手机。浏览器对合成批次先扣 0.5、再快速双击扣 0.1，最终剩余 1.4、共 3 条流水（含入库），未发现页面脚本错误。停止本地服务后尝试提交，页面保留输入 0.2 并显示“结果待核对”，合成库余额仍为 1.4；退出后浏览器后退回到登录页。
- 独立无缓存 loopback HTTP 测量：合成首页 HTML + CSS + JS 原始响应体合计 10,815 字节；库存页 27,815 字节。这不是手机 Wi-Fi 传输量、压缩后大小或 LCP/INP/CLS 测量。
- 阶段 04 后续通过 Windows 管理员提升，将仓库 `config/Caddyfile` 备份验证后应用到服务配置；备份保存在私有 `C:\ProgramData\ShiJinQiYong\Caddyfile.stage04-20260925-143749.bak`。服务仍以 LocalService 运行并绑定 `192.168.1.127:8443`。使用公开根 CA 实际核验：指纹 CSS 和两个 JS 返回 `Cache-Control: public, max-age=31536000, immutable` 与 `Content-Encoding: gzip`；动态健康/API 响应继续 `no-store`。没有复制或导出 CA 私钥。
- Caddy 重启后的第一次动态探测曾返回 502；当时 Waitress 不再监听 loopback。改用持续的本机终端会话重新运行 `scripts/start_waitress.ps1` 后，可信 HTTPS `/health/` 为 200、匿名 `/` 为 302、匿名 `/api/today/` 为 401。Waitress 仍依赖该会话，关机或关闭会话后的恢复没有验收。

## 拍照录入补充

- 本机已有 Ollama 0.32.1 和 `qwen3-vl:8b` 模型；识别接口固定连接 `127.0.0.1:11434`，实测该端口仅监听 loopback。Ollama 的启动与登录/重启恢复尚未配置或验收；进程不在时拍照识别返回 503，手工录入仍可用。
- 新增 `Pillow==12.3.0`，浏览器端先缩图，服务端只接受 JPEG/PNG/WebP、最多 2.5 MB 原图与 2,000 万像素，并在内存中重新编码去元数据。照片仅送至本机模型；未建立持久图片存储或在线 AI 连接。
- Caddy 的照片路径允许 4 MB，请求其余路径仍限 64 KB；Waitress 上限为 4 MB。应用未新增局域网监听端口、路由器映射或防火墙规则。
- Caddy 新配置第一次管理员应用时，PowerShell 将校验程序的 stderr 信息作为错误，已恢复旧配置；修正脚本后应用了新配置，但服务管理器一度停在 `StartPending`。经管理员核实运行进程后重启该服务，目前为 `Running`，仍是原 `LocalService` 和相同 CA。使用公开根证书再次核对 `/health/` 200、照片路径 70 KB 匿名请求 401、普通库存路径 70 KB 请求 413。该过程不代表主机重启恢复已验收。

## 阶段 05 补充

- 本地菜谱使用随源码交付的 JSON 文件，没有外部菜谱服务或新模型。读页面只读取 SQLite 库存；实际用量通过原多批次事务动作扣减并写流水。
- 本阶段没有数据库迁移和新局域网端口。实施前通过 `sqlite3.backup` 创建私有 `data/backups/stage04-before-stage05.sqlite3`，备份完整性和外键检查通过。只读核对时生产库仍为 2 个成员账号、0 个批次、0 个业务动作；合成食材只存在测试库。
- 菜谱匹配与做饭写入共用家庭时区日期。包装日期过去、储存待核对、疑似变质和零余额批次均不能作为可用食材；“已找到”只表示名称匹配，不是食用安全或份量判断。
- 阶段 05 的真实手机浏览、实际食材匹配及确认后流水，仍需用户在可信家庭 Wi-Fi 上验收；自动化测试不构成现场结果。
- CSS 已重新收集并生成新指纹文件，Waitress 在当前持续终端会话重启；Caddy 的 `192.168.1.127:8443` 配置、CA 与防火墙范围未改。以公开根 CA 验证的本机 HTTPS 请求得到 `/health/` 200、匿名菜谱页 302、匿名菜谱 API 401、新指纹 CSS 200 且长期缓存；未登录请求没有测试实际菜谱提交流程。

## 家庭菜谱、分类与私有附件补充

- 用户明确选择**同时支持外部视频链接与本机视频上传**，单个本机视频上限 200 MiB。家庭菜谱文字、分类、标签和链接进入本机 SQLite；图片与视频保存在 `data/recipe_media/`，不由 Caddy `/static/` 暴露。图片重编码去元数据，视频保留原字节，可能保留原视频元数据。服务端不抓取外站内容；外部搜索只在成员点击时由浏览器发出。
- 迁移前用 SQLite backup API 创建私有 `data/backups/stage05-before-family-recipes.sqlite3`，完整性与外键检查通过。随后应用 `meals.0001_initial`，退出码 0。迁移后只读检查：`integrity_check=ok`、外键错误 0、现有账号 2、真实批次 1、家庭菜谱 0、媒体 0；没有把合成菜谱或文件写入生产库。
- Caddy 管理员配置备份为私有 `C:\ProgramData\ShiJinQiYong\Caddyfile.family-20260925-163444.bak`，新配置已验证并应用，服务仍为 `Running`、同一 CA 与 8443 入口。仅家庭菜谱上传路径允许 220 MB，拍照识别路径仍为 4 MB，其余普通请求 64 KiB；Waitress 仍只监听 loopback，接收上限增至 220 MB。使用公开根 CA、没有关闭证书校验：`/health/` 200、匿名 `/recipes/` 与 `/recipes/new/` 302、匿名菜谱 API 401、指纹 CSS/新 JS 200；匿名上传路径 70 KB 返回 302（到达登录门）、普通库存路径 70 KB 返回 413。该探测不包含已登录上传或真实手机播放。
- 备份工具 `backup_household` 的合成测试复制并核对 1 个示例附件。实际停止 Waitress 后运行生产私有备份，生成 `data/backups/household-20260925-163913-84e6e941/`，数据库及 0 个当前附件检查通过；恢复 Waitress 后，公开根 CA 验证的 `/health/` 为 200。Waitress 正运行时再次调用备份命令会拒绝，实际退出码 1，符合阻止不一致快照的约定。异设备复制及从备份恢复仍未执行。
- 生产 Waitress 依赖当前持续终端会话，主机或会话重启恢复尚未验收。200 MiB 实际手机上传、图片显示、视频 Range 播放、不同浏览器格式兼容性、家庭内容真实隐私检查与真实设备交互均未执行；当前证据来自隔离测试库和匿名 HTTPS 探测。

## 阶段 07 当前运行状态（2026-09-25）

以上早期地址和服务方式保留为当时记录；**当前值以本节为准**。

- 用户确认新的 `192.168.110.146/24` 是家庭 WLAN。Caddy 已改为仅监听 `192.168.110.146:8443`，仍使用同一家庭根 CA；Django 私有运行配置中的 Host 与 CSRF Origin 已同步。管理员操作前分别备份私有运行配置和 Caddy 配置；Caddy 的阶段 07 配置备份位于 `C:\ProgramData\ShiJinQiYong\Caddyfile.stage07-20260925-191840.bak`。原 `192.168.1.127` 已不在电脑 WLAN 上。
- 入站规则 `ShiJinQiYong-Caddy-HTTPS-8443-WLAN` 当前启用，仅放行 Caddy 程序、WLAN、TCP 8443、本机 `192.168.110.146` 与来源 `192.168.110.0/24`；WLAN 的 Windows 网络类别仍为 Public。Caddy 以 `LocalService` 运行，服务启动类型现为 Automatic。80/443 端口及路由器未修改。
- Waitress 和 Ollama 为当前 Windows 用户的交互式登录任务 `ShiJinQiYong-Waitress`、`ShiJinQiYong-Ollama`，分别只监听 `127.0.0.1:8000` 与 `127.0.0.1:11434`。启动脚本对意外退出限速重启；两个子进程各中断一次后均在数秒内恢复。任务仅在用户登录后启动，整机重启及未登录状态没有实测。
- 用同一公开根 CA 验证新地址的本机 HTTPS 请求：健康页 200、登录页 200、匿名采购页 302、匿名采购 API 401、匿名菜谱 API 401、指纹静态文件 200、普通路径超大请求 413。根证书与早期公开测试证书的文件 SHA-256 相同；证书的 DER SHA-256 指纹仍为 `5A:49:BD:03:CC:C8:2B:8F:C3:55:77:23:3A:F2:FA:27:1B:FE:F6:D9:2A:C7:6F:04:12:71:09:75:74:D6:EE:FF`。
- 用户随后确认手机能打开新地址，但提示证书不受信任。这是当前现场阻断项；本机成功不等于手机证书验收。需按 `HANDOFF.md` 安装并启用手机对公开根 CA 的信任，不能跳过警告登录。阶段 06 的手机采购流程也尚未验收。
- 生产 SQLite 只读完整性、外键、库存流水余额/链条、采购入库关联检查通过；完整 64 项测试通过。最新阶段 07 私有备份为 `data/backups/household-20260925-192704-bb25d42c/`，附件当前 0 个；从该备份恢复到独立 `work/` 目录，通过完整性、业务计数、会话清理和四页面读取。未切换生产库，也未建立异设备副本。详情见 `PROGRESS.md`。

## 固定局域网入口（2026-09-26）

当前入口为 `https://shijinyong.local:8443/`，已确认的 WLAN “White Whale” 为 `192.168.1.220/24`。上面阶段 07 的 IP、规则和启动方式保留为历史记录，当前以本节为准。Caddy 仍以 `LocalService` 运行，手动启动类型交由受保护的 `ShiJinQiYong-NetworkGuard` 系统任务控制；防火墙 TCP 8443 规则限定当前 WLAN IPv4、Caddy 程序和同一子网。当前用户的 `ShiJinQiYong-LanName` 登录任务从守护状态读取地址并通过 mDNS 发布 `.local` 名称，另有仅针对该程序的 WLAN UDP 5353 入站规则。Django 生产 Host 与 CSRF Origin 已更新为固定名称，旧配置在私有备份目录。

电脑 `Resolve-DnsName` 得到 `192.168.1.220`，严格使用公开根 CA 验证的 TLS 1.3 证书含 `shijinyong.local` SAN，`/health/` 200、`/login/` 200、匿名采购 API 401；Waitress 仍只监听 loopback。网络守护每 4 秒更新状态；合成未知 AP BSSID 的只读模拟返回 `trusted=none`。实际更换到未知 Wi-Fi、DHCP 换地址、整机重启及 Android 手机固定名称访问尚未通过验证。用户首次手机测试反馈固定网址“无法打开”，具体浏览器错误和 IP 直连结果待反馈；不能把本机结果当作手机上线结果。Caddy 在 Windows 的监听记录是 `::`，但当前 IPv4 可连；网络接入范围以防火墙 IPv4 规则为准，仍需实际外部设备检查。守护任务异常退出时既有规则不会自动过期，这是后续运行风险。

## 当前 IP 入口恢复（2026-09-26）

用户要求暂停固定名称方案，恢复原来的 IP 访问。**当前状态以本节为准**：Caddy 以 `LocalService` 运行，启动类型 Automatic，只监听 `192.168.1.220:8443`；TCP 入站规则限定 Caddy 程序、WLAN、该地址与 `192.168.1.0/24` 来源。名称发布任务、网络守护任务均已停用，mDNS UDP 5353 入站规则禁用，名称发布子进程已停止。Django 私有 Host/CSRF Origin 已备份后改回当前 IP，Waitress 已重启并只监听 `127.0.0.1:8000`。当前家庭根 CA 严格校验下的电脑请求得到 `/health/` 200、`/login/` 200、匿名 `/shopping/` 302、匿名采购 API 401；手机重新测试待反馈。固定名称实验中原定的 `shijinyong.local` 少了“其”的拼音 `qi`，用户截图尝试的 `shijinqiyong.local` 才是完整名称；两者均不是当前入口。更换 Wi-Fi 或 IP 后须先由用户确认，再人工调整配置与规则。

手机随后测试当前 IP 的 `/health/`：先提示证书警告，点击继续后显示 `ok`。可达性已实测，手机对家庭根 CA 的无警告信任未通过，尚不能安全登录。`outputs/current-ip-source.zip` 为 121 个文件的源码与文档快照，不包含 `data/`、运行配置、数据库、私有媒体、证书私钥或日志；不能代替家庭数据备份。

## 阶段 07A 当前网络与运行（2026-09-26）

本节取代上文历史地址说明。用户先前确认的当前家庭 WLAN 为 `192.168.110.146/24`；Caddy `ShiJinQiYongCaddy` 以 `LocalService` 运行，仅在该地址开放 8443，防火墙规则限定 Caddy 程序、WLAN、本机地址和 `192.168.110.0/24` 来源。Waitress 只监听 `127.0.0.1:8000`；旧 `.local` 名称发布和网络守护实验仍停用。Django 私有 Host/CSRF Origin 已同步新地址，Caddy 配置及运行配置变更前都有私有备份。用户报告 Android 打开 `https://192.168.110.146:8443/health/` 仍有证书警告；不能据电脑持根 CA 的成功请求宣称手机可信 HTTPS 已验收。

阶段 07A 生产迁移 `meals.0002` 至 `0005` 已应用；8 道内置结构化菜谱来自版本化文件，14 项营养来源经 `0003` 入库。外部生成默认关闭，当前无真实模型调用或常驻菜谱工作进程。生产私有备份 `household-20260926-211032-0a7d6254` 已独立恢复核验；源码包与数据备份分开。准确的代码状态、测试、性能及未完成项见 `PROGRESS.md`、`ACCEPTANCE.md`、`PERFORMANCE.md`。
