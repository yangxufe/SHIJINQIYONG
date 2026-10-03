# 2026-10-03 现行补充

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
