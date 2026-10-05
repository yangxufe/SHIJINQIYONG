# 2026-10-05 第三次优化交接

首页四入口依次为添加菜品、食材列表、查看菜谱、采购计划。添加页为 /inventory/，原批次卡片/搜索/操作移至 /inventory/list/；保存后到列表。保质期可切换截止日期或天数，天数必须有用户明确的起算日期，服务端算出并只保存截止日期；后续在编辑页修改截止日期。未填日期为未知，新录入继续储存待核对，核对后才可能用于推荐。菜谱四类保留原家庭内容及旧分类链接，采购确认、库存事务和原权限不变。

本轮无迁移/新依赖。实际生产备份 household-20261005-195704-1f92a1b9（0 附件），本地回退标记 rollback-before-third-optimization-20261005 对应 516f80a；备份不上传。121 项完整回归通过，20 张账号及业务表与备份逐行一致；生产迁移无待执行项，静态文件已收集，Waitress Running、仅 loopback 8000，11 项最小运行检查通过。更新继续使用下方安全停止 → 备份 → 更新代码 → migrate → collectstatic → 启动流程；界面回退无需恢复数据库，切回基线并重新 collectstatic/重启即可。不要将全库恢复当作界面回退，以免丢失备份后的真实记录。

**浏览器验收已补齐：**用户打开正常页后，独立合成账号完成保质期两模式、保存/返回/搜索、批次用量、菜谱分类与独立教程搜索、采购确认和唯一入库。五页 320/390/1280 宽度无溢出、标题不重叠；采购短链接折行已修复并在用户刷新旧 CSS 后复验通过。修复后 15 项针对性回归通过，已再次收集静态文件并重启生产应用，原生产数据核对未变。详情与本机真实截图路径见 PROGRESS/ACCEPTANCE/BVT。

Android 证书工作按用户要求暂缓，不更改 CA、网络或防火墙；下方信任步骤留作日后续办，不把本轮源码更新说成手机 HTTPS 已通过。第三次优化代码 77fd602 及浏览器补验修复 1f9108b 均已推送 GitHub main 并核对远端，本同步记录另随文档提交；下载取最新 main。同步的实际检查记录见 PROGRESS.md。验收结束已退出合成账号、恢复浏览器尺寸并停止测试 8766 服务；该测试地址不再是运行入口，正式 Waitress 继续仅监听 loopback 8000。

## 2026-10-04 Caddy 恢复与 Android 信任交接（历史）

现行入口 `https://192.168.110.146:8443/`。已在此前确认的家庭 WLAN 核对并启动 Caddy，状态 Running/Automatic、仅监听 192.168.110.146:8443；Waitress 仅 127.0.0.1:8000。电脑端 30 项 HTTPS 补测通过，所有 27 次连接校验证书链与 IP；配置、CA 和防火墙范围未变，原生产数据只读比较不变。详见 BVT.md/PROGRESS.md。下方“Caddy 停止”是先前时点的历史记录。

**尚未通过手机信任：**当前 Android Chrome 截图为 NET::ERR_CERT_AUTHORITY_INVALID。此错误说明已连到 TLS 服务，但客户端未信任颁发机构；不是需要继续扩大端口或换 CA 的证据。不要在浏览器警告后继续输入密码。按 AGENTS.md，安装设备根证书须使用者许可与系统操作，程序不会替你自动安装。

## 原主机的 Android 人工步骤

1. 仅在你同意让手机信任本机 Caddy CA 后，将原主机项目中的 `outputs/shijinqiyong-root.cer` 通过自己核对的 USB 或已有可信文件传递方式存到手机。该文件仅含公开证书，不含私钥；不要传递整个 CaddyData 目录。其他电脑独立安装有自己的 CA，不能混用这个文件。
2. 在原电脑运行 `Get-FileHash .\outputs\shijinqiyong-root.cer -Algorithm SHA256`，应为 `5A49BD03CCC82B8FC35577233AF2FA271BFEF6D92AC76F041271097574D6EEFF`。这是 **DER 文件/证书的 SHA-256**，不同于 PEM 文件哈希或 SHA-1。证书主体应为 `Caddy Local Authority - 2026 ECC Root`。手机证书查看器若显示 SHA-256，应与同一指纹一致；文件来源或指纹不明时先停止。
3. 在 Android 系统设置搜索“CA 证书”或“安装证书”；常见路径为“安全与隐私 → 更多安全设置 → 加密与凭据 → 安装证书 → CA 证书”，选择上面的公开文件。不同厂商菜单名称不同，须选 **CA 证书**。Android 安装时可能提示此 CA 能签发被设备信任的证书，阅读并自行确认；这是设备信任设置，不是在 Chrome 网页里跳过安全警告。[Google 的 CA 证书安装说明](https://support.google.com/device-usage-study-help/answer/15713321?co=GENIE.Platform%3DAndroid&hl=en)中相应系统步骤可参考，无需安装该页面介绍的研究应用或 VPN。
4. 关闭 Chrome 后重新打开，在同一可信 Wi-Fi 访问 `https://192.168.110.146:8443/health/`，应无证书警告并显示 `{"status":"ok"}`。仅安装文件、看到系统安装成功或点击网页“继续”均不足以通过这个检查；[Caddy 官方说明](https://caddyserver.com/docs/automatic-https#local-https)要求每个客户端分别信任内部 CA。
5. 如仍报错，检查安装的是当前公开根、系统“受信任的凭据 → 用户”里该 CA 已启用，且手机日期时间正确；仅反馈手机系统/浏览器版本及完整错误码，不发密码、Cookie 或私钥。受管手机不允许添加 CA 时不要绕过策略。无警告后再测试登录、三个入口和采购闭环，并将健康页结果发回。

不再使用时，可在 Android 的用户凭据/受信任凭据中移除这一项；不要执行“清除全部凭据”。这份 CA 的信任适用于它签发的证书，并非只授权单一页面。本轮手机安装、无警告健康、登录与采购仍未执行或通过；服务已运行不等于完整发布验收。

## 2026-10-04 第二次优化交接（恢复前记录）

当前四层入口：封面 → 登录/邀请注册 → 内部首页 → 添加菜品、查看菜谱、采购计划。三个功能页左上返回首页，右上家庭设置与 POST 退出；原库存、菜谱、采购路由不变，旧底部导航和路径式标题已移除。新注册用户名最多 10 字符、密码至少 8 字符并通过其他 Django 校验；已有长账号、密码哈希和数据不变。密码框眼睛只显示 1 秒，失焦/离页立即隐藏。

本轮代码 b5deb6e 已推送 GitHub main 并核对远端；本记录另随文档提交，下载/拉取取最新 main。Waitress 已按安全停止流程更新重启，生产迁移无待执行项、静态文件已收集，匿名 loopback 健康/登录/注册 200、库存/菜谱 API 401；10 张业务/账号表与私有备份逐行一致，数据库完整性通过。这是本机诊断，Caddy 仍停止，未完成真实手机或 Mac 访问验收。

本轮不含数据库迁移，更新沿用下方停止 → migrate → collectstatic → 启动步骤，务必先等待停止检查成功。回退标记 rollback-before-second-optimization-20261004 对应 e1f1e2a，私有备份 household-20261004-130018-a21a03b8（0 附件）；回退界面无需恢复数据库。113 项自动化及 320/390/1280 宽度浏览器操作已通过，真实 Android/macOS 尚未执行。运行与同步的最终记录见 PROGRESS.md。

食品视觉继续使用本机 YOLO，未改模型/CA/防火墙。原手机证书警告与 Caddy 停止待办继续保留；源码更新不等同于 LAN HTTPS 验收。请在可信 HTTPS 下人工确认新导航与手机眼睛按钮，首次新成员注册仍需管理员邀请。

## 2026-10-03 历史补充

首次优化代码与兼容 core.0002 迁移已执行，原数据与迁移前私有备份逐行核对不变。YOLO 已构建/安装本机，使用说明见 [YOLO.md](YOLO.md)，不需要视觉 Ollama。复制安装模型时与原数据相互独立。

2026-10-03 恢复会话权限后已修复并实际验证 Waitress 重启。原计划任务停止会留下 Windows venv 基础解释器子进程，旧代码曾继续返回 500；停止脚本现核对本项目解释器、Waitress 模块、父子关系和进程创建时间，清空 8000 后再启动任务。loopback 的 /health/、/welcome/、/login/、/register/ 为 200，匿名库存和菜谱 API 为 401；这是本机代理诊断，不是手机 HTTPS 验收。Caddy 服务仍停止，本轮未启动局域网入口、未改网段、CA 或防火墙。下面旧日期的启动状态与旧 IP 是历史记录。

代码更新后的重启请使用以下步骤。停止脚本必须成功并确认 8000 不再监听后才能更新/备份；不能只依据任务状态或提前启动：

```powershell
& scripts/stop_waitress_for_backup.ps1
# 此处按 WINDOWS.md / YOLO.md 更新、迁移、收集静态文件。
Start-ScheduledTask -TaskName ShiJinQiYong-Waitress
```

若需手机访问，在已确认可信 Wi-Fi 下按 WINDOWS.md 启动 Caddy，并用已信任的公开根证书检查 HTTPS health。手机无警告信任仍未验收，不要越过证书警告输入密码。最新停机后私有备份为 household-20261003-182858-848124d8，附件 0 个，未上传。

## 更新与回退

1. 先按既有流程停止 Waitress，并 backup_household；本輪迁移前备份 household-20261003-120320-1c2099e8 位于受保护 data/backups，已核验完整性，未上传。
2. 更新源码后安装 requirements.lock、执行 migrate、collectstatic、安装 YOLO；见 WINDOWS.md/MACOS.md/YOLO.md。保持原 runtime.env、SQLite、家庭附件和 CA，不重新初始化。
3. Git 代码基线为 c524328，本机回退标记 rollback-before-first-optimization-20261003。core.0002 只建邀请表，回退旧代码无需删除它，原账户/库存/采购/菜谱兼容；注册产生的新成员仍为旧版支持的 MemberRole。
4. 若确需撤销邀请注册，停止服务后可在核对注册期间数据及备份后迁移 core 到 0001，但该操作会删除邀请记录，不能盲目执行或连带清空原家庭数据。若恢复迁移前全库，会丢失备份后真实变更，需人工确认。
5. 模型文件可重新从仓库校验安装；自定义旧模型安装脚本拒绝覆盖。切换模型前停应用、保存旧模型与清单。不要为了模型回退恢复旧库存数据库。

## GitHub 交付状态

先前会话的 .git 只读与网络限制已由用户解除。本轮 68 文件优化提交 10555bf14d275a270a279fdec1680eda64cde332 已通过 Git CLI 推送至 yangxufe/SHIJINQIYONG 的 main，ls-remote 核对通过；随后从 GitHub 独立浅克隆取得相同提交，完整 ONNX 模型及安装副本 SHA-256 一致。下载请取当前最新 main，后续交付文档另有小提交；证据见 PROGRESS.md。data/、.venv、work、outputs、运行密钥、照片和私有备份未上传。没有使用另一位协作者账号测试访问权限；协作者仍需拥有此仓库的读取权限。

---

# 食尽其用：家庭运行交接

更新：2026-09-26。**现行入口 `https://192.168.110.146:8443/`**，在此前确认的家庭 Wi-Fi 上由 Caddy 开放；Android 仍有证书警告，不能算安全登录验收。下方阶段 07 旧地址说明保留为历史记录，当前运行与阶段 07A 步骤以文末补充为准。实际检查与未完成项见 `PROGRESS.md`。

## 入口与运行

- 阶段 07 历史手机入口：`https://192.168.1.220:8443/`。当前已确认的家庭 Wi-Fi 是“White Whale”，电脑地址为 `192.168.1.220/24`。手机和电脑须在同一个网络。固定名称实验已按用户要求暂停；网络地址变化时入口不会自动更新，先确认新网络再调整 Caddy、Django 与防火墙。
- 手机必须连接同一家庭 Wi-Fi，并信任家庭根证书 `outputs/shijinqiyong-root.crt`；同目录的 `shijinqiyong-root.cer` 是同一公开证书的 DER 格式，便于手机导入。安装前核对证书的 **DER SHA-256 指纹**：`5A:49:BD:03:CC:C8:2B:8F:C3:55:77:23:3A:F2:FA:27:1B:FE:F6:D9:2A:C7:6F:04:12:71:09:75:74:D6:EE:FF`。只分发公开证书，不分发 CA 私钥；出现证书警告时不要继续输入密码。
- Caddy Windows 服务名为 `ShiJinQiYongCaddy`，以 `LocalService` 运行，启动类型为自动，监听 `192.168.1.220:8443`。入站规则 `ShiJinQiYong-Caddy-HTTPS-8443-WLAN` 限定 Caddy 程序、WLAN、TCP 8443、当前电脑 IPv4 与 `192.168.1.0/24` 来源。名称发布 UDP 5353 规则已禁用。Waitress 和 Ollama 分别只监听 `127.0.0.1:8000`、`127.0.0.1:11434`。
- `ShiJinQiYong-Waitress` 与 `ShiJinQiYong-Ollama` 是当前 Windows 用户的登录任务。`ShiJinQiYong-LanName` 与受保护的 `ShiJinQiYong-NetworkGuard` 已停用。主机重启后的任务、证书和手机访问尚未实测。

## 手机仍需验收

用户确认 Android 手机访问当前 `https://192.168.1.220:8443/health/` 会先出现证书警告，点继续后显示 `ok`。这只验证了局域网连通，**正式登录仍未达到可信 HTTPS 条件**；不要在忽略警告后输入账号密码。电脑端持同一公开根 CA 验证 `/health/` 返回 200。先核对手机系统的 CA 证书安装与信任状态；若安装后仍报警，请记录浏览器的完整错误文字和手机时间。

Android 截图中的 `ERR_NAME_NOT_RESOLVED` 属于拼写不一致的固定名称实验；截图顶部虽然显示 IP 地址，错误详情仍是先前域名，不能据此判定 IP 连通失败。手机当前地址 `192.168.1.216` 与电脑同网段，电脑向手机发出的测试网络回应成功。请用当前 IP 入口重新测试，记录原始浏览器错误；不能通过放宽到所有网络或关闭防火墙解决。证书警告出现时不要登录。

- **iPhone/iPad：**通过可信方式把公开 `.cer` 传到手机，安装下载的证书配置描述文件；在“设置 → 通用 → VPN 与设备管理”可查看已安装描述文件。然后到“设置 → 通用 → 关于本机 → 证书信任设置”，在根证书下为该证书启用完全信任。手动安装的描述文件不会自动取得 SSL 信任；如果根证书信任开关不出现，说明尚未安装额外证书。参见 [Apple 的安装说明](https://support.apple.com/en-hk/102400)和[信任说明](https://support.apple.com/en-au/102390)。
- **Android：**把公开证书存到手机，进入系统设置中的“安全与隐私 → 更多安全设置 → 加密与凭据 → 安装证书 → CA 证书”，选择该文件；不同厂商的菜单名称可能不同。请选 **CA 证书**，不要选 Wi-Fi 或 VPN 用户证书。参见 [Google 的 Android CA 导入步骤](https://support.google.com/device-usage-study-help/answer/15713321?co=GENIE.Platform%3DAndroid&hl=en)。

当前 IP 地址无警告登录后，用一条真实采购项检查：

1. 添加采购项，留意现有库存与同名待买提示。
2. 点“买到了”，确认冰箱库存没有增加。
3. 按实际数量确认入库一次，检查新批次和正向流水；再次提交不能重复入库。
4. 如家中有第二台设备或第二名成员，交叉查看同一记录。遇到结果待核对时沿用原请求编号重试。

采购手机流程与当前地址证书仍未通过验收；不得把电脑端自动化测试记为现场通过。真实照片识别准确率、200 MiB 视频上传、主机重启恢复也尚未现场验收。

## 日常检查

在项目目录的 PowerShell 中检查：

```powershell
Get-Service ShiJinQiYongCaddy
Get-ScheduledTask -TaskName ShiJinQiYong-Waitress,ShiJinQiYong-Ollama
Get-NetTCPConnection -State Listen -LocalPort 8443,8000,11434
```

若登录任务未运行，可分别执行 `Start-ScheduledTask ShiJinQiYong-Waitress`、`Start-ScheduledTask ShiJinQiYong-Ollama`。Caddy 与防火墙需要管理员权限管理；不要把 Waitress 或 Ollama 改为局域网监听。未来新 Wi-Fi 先由用户确认，再按实际 IP、子网更新 Caddy、Django 和入站规则。固定名称相关任务保持停用，待用户另行要求再继续。应用检查命令为 `& scripts/manage_prod.ps1 check --deploy`；现有 `security.W004` HSTS 警告已记录。

## 备份与恢复

数据库和家庭菜谱附件必须作为一组备份。短暂停止应用写入，然后备份并恢复服务：

```powershell
& scripts/stop_waitress_for_backup.ps1
& scripts/manage_prod.ps1 backup_household
Start-ScheduledTask ShiJinQiYong-Waitress
```

备份会在私有 `data/backups/household-*` 目录写入 SQLite、所有被数据库引用的附件和清单，并核对完整性及 SHA-256。备份完成后检查 Waitress 登录任务及可信 HTTPS 健康页。保留整个备份目录；另存到受保护的异设备，并实际检查该副本可读。当前只完成本机私有备份和独立目录恢复演练，异设备副本未执行。

恢复前先停止 Waitress，并保留当前生产数据库与附件的完整副本。只使用通过完整性、外键与附件摘要检查的备份；将数据库和附件一起恢复，清除旧 `django_session`，按 `README.md` 的命令检查迁移与部署，再启动 Waitress 验证登录、冰箱、做什么和采购。阶段 07 的恢复演练使用 `work/` 中独立副本，没有覆盖生产数据；真正故障时的生产切换需按故障现场再执行和核验。

`data/`、`data/runtime.env`、私有备份、上传媒体、密码、Cookie、日志和 CA 私钥不得进入源码 ZIP 或公开目录。`outputs/stage07-source.zip` 只用于交接源代码，不能代替家庭数据备份。

## 阶段 07A 当前操作补充

- 当前已确认的 WLAN IPv4 为 `192.168.110.146/24`，Caddy 只接受该地址的 8443；入站规则限 Caddy 程序、WLAN、本机地址和 `192.168.110.0/24` 来源。Waitress 仍只在 `127.0.0.1:8000`。固定名称与 mDNS 任务保持禁用。换网络时先确认新网络，再同步 Caddy、Django Host/CSRF Origin 和防火墙范围，不能直接在未知 Wi-Fi 放行。
- Android 访问 `https://192.168.110.146:8443/health/` 仍提示证书不受信任。把 `outputs/shijinqiyong-root.cer` 这一**公开** CA 文件通过可信方式送到手机，以 Android 系统的“CA 证书”类型安装；核对上面的 DER SHA-256 指纹、手机时间和证书警告详情，再在浏览器无警告访问 `/health/`。不要分发 CA 私钥，也不要在警告后输入账号密码。
- “做什么”中的工作台先解释自然语言，再让成员改选并确认条件；严格库存模式核对调料和器材，允许补购模式只显示选中菜单的净缺口。购物加入和实际做饭均需再次确认。原列表仍保留旧名称匹配入口，准确数量判断请使用工作台。
- 可选生成默认关闭。`config/recipe-provider.example.env` 只列配置名；管理员将真实模型名、选择的提供者和凭据放入受保护的 `data/runtime.env`，绝不可放在网页、源码包或普通日志。要使用外部生成时，还需当前用户在页面上同意发送本次最少条件和可用库存摘要。运行进程为 `& scripts/start_recipe_worker.ps1`，一个工作进程默认单任务并发；先在隔离环境联调，再托管。现在未启动，也没有真实模型调用。任务取消不能保证供应商已接收请求后不计费；异常重启后由工作命令处理超时失联任务，不要无限重试。
- 最新阶段 07A 生产备份为私有 `data/backups/household-20260926-211032-0a7d6254/`，已恢复到另一个私有目录并检查。现行源码包将另行生成 `outputs/stage07a-source.zip`；其用途仍与数据库/附件备份不同。回退时先停止 Waitress，保留当前 `data/` 原件，恢复**备份中的数据库和媒体一起**，清掉旧会话，核对完整性、外键、迁移和账号，再恢复服务。旧版本代码不能直接读取已迁移的 07A 数据；必须使用相容的 07A 代码，或连同 07A 前私有备份 `household-20260926-201734-d24936b8/` 一起回退，后者会丢失备份时间之后的写入。不得把生产库直接覆盖为测试副本。
- 阶段 07A 自动化、性能和现场余项见 `ACCEPTANCE.md`、`PERFORMANCE.md`、`SECURITY.md`。主机重启、异设备备份、手机采购闭环与无警告 HTTPS 仍待现场完成；阶段 08 完整发布验收尚未通过。
