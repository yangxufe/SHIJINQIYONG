# BVT 构建验证记录

## 第三次优化增量验证（2026-10-05）

本轮完整 `manage.py test tests --settings=config.settings.test --noinput` **121 项通过，20.145 秒，退出码 0**；此前针对性 27 项通过。新增验证覆盖独立食材列表、日期/天数录入规范化、闰日/范围、CSRF/权限、旧版本/幂等、分类和采购确认；旧真实文件 SQLite 并发测试保留。无模型迁移差异。

实际停止/更新/collectstatic/重启 Waitress 后，11 项本机代理头 HTTP 检查通过；20 张账号及业务表与本轮私有备份逐行一致，完整性和外键检查通过。两项 JS 和 SVG 指纹文件与源码一致，CSS 的本地 SVG URL 后处理正常；check --deploy 只有既有 security.W004。普通模板及资源已部署，Caddy/证书/防火墙未调整。

**本轮浏览器 BVT 未完成：**工具拒绝控制现有 data: 内置错误标签，等待用户手动打开独立测试登录页。按钮和窄屏布局、真实截图尚未执行；下方 10 月 4 日浏览器结果是旧版本历史证据。Android 证书工作按用户要求暂停，本轮也不是性能压测或完整发布验收。

## 2026-10-04 历史基线

日期：2026-10-04（Asia/Shanghai）。基线：52fcd2cf8fe22b2bc81569b9f2893731fac3fa15，开始时工作树干净。本轮执行一次完整回归、运行检查和浏览器核心流程；修复两处残留文案后，执行针对性复测。

**当日结论：核心构建与电脑端严格校验的 HTTPS 补测通过；Android CA 信任仍阻塞，不能标为完整发布通过。** Caddy 已恢复，下方原始构建结果与恢复前状态保留。

## Caddy / HTTPS 补测（2026-10-04）

起点 7f41d09、干净工作树，沿用已确认的 192.168.110.146/24 家庭 WLAN。经 UAC 核对受保护配置、原 CA 和现有防火墙范围后启动 ShiJinQiYongCaddy，Running/Automatic；Caddy 仅监听 192.168.110.146:8443，Waitress 仅 127.0.0.1:8000，管理端口 2019 无监听。没有变更配置、信任库、网络或规则。

本机 `work/https_bvt_20261004.py` 用生产设置、Python 标准 TLS 和现有公开 CA 执行，最终退出码 0：**30 项检查、27 次严格验证的实际 HTTPS 连接通过**。此脚本与安全结果留在本机被忽略的 work/；基本健康校验入口见 WINDOWS.md 第 5 节，不需要关闭证书验证。

| 补测 | 实际结果 |
|---|---|
| 证书链、主机名及 IP SAN | CERT_REQUIRED、check_hostname；SAN 包含 192.168.110.146，每次使用 TLS 1.2/1.3；公开 PEM 和 DER 相同、根指纹与原记录一致 |
| 公共页与动态策略 | health/welcome/login/register 200，health 仅 status=ok；no-store、原 CSP、DENY/nosniff；CSRF Cookie Secure、SameSite=Lax |
| 鉴权及 CSRF | 根跳封面、五个业务入口跳登录；五个匿名读 API 和一个匿名写 API 401；缺 CSRF 的登录/注册 POST 403 |
| 静态资源 | CSS、密码按钮、库存、菜谱搜索四个指纹文件 200，与源码 SHA-256 一致，缓存 immutable 一年；非指纹 no-store，缺文件 404 |
| 代理边界 | 70 KB 普通 POST 413；伪造 Forwarded/协议头不改变 HTTPS 处理；非站点 Host 返回 Caddy 空 200，不路由 Django，也不返回健康内容 |
| 真实数据 | 补测后只读核对 10 表与私有备份逐行相同，完整性 ok、外键问题 0；未登录真实账号或成功写业务数据 |
| Android 现场 | 用户截图 NET::ERR_CERT_AUTHORITY_INVALID，确认可达但未信任 CA；手机可信登录和采购闭环仍未执行 |

两次诊断失败保留：首次管理员辅助脚本把正常 Caddy stderr 当异常，启动前退出，修正包装捕获后按退出码验证并成功启动；首次 HTTPS 探测对非站点 Host 的 400/404 预期不符，实测空 200，核对确实未路由应用后校正探测合同再通过，没有修改服务器行为或隐藏失败。电脑显式信任 CA 的探测不等于 Android/系统浏览器已经信任；手机安装步骤与指纹见 HANDOFF.md。本次不重复完整单元回归，不新增迁移；性能压测、重启恢复和完整阶段 08 验收未执行。

## 实际结果

| 检查 | 结果 | 证据 |
|---|---|---|
| 完整自动化回归 | 通过 | 113 项，17.231 秒，退出码 0；含认证/CSRF/邀请、库存/流水/并发/幂等、采购、菜谱权限/菜单、YOLO 输入/安装等检查 |
| 依赖和迁移 | 通过 | pip check 无冲突；生产 migrate --check 退出码 0，无未应用迁移；makemigrations --check --dry-run 无差异 |
| 生产安全检查 | 有既有警告 | check --deploy 退出码 0，只有 security.W004（IP HTTPS 尚未设置 HSTS）；未屏蔽或关闭安全检查 |
| Waitress 最小运行检查 | 通过 | 任务 Running，仅监听 127.0.0.1:8000；health/welcome/login/register 200、health=ok；匿名库存/菜谱 API 401 |
| 静态资源与响应头 | 通过 | CSS、密码按钮、库存和菜谱搜索 4 个指纹文件存在且与当前源码 SHA-256 一致；生产登录/注册引用指纹，含 no-store、CSP，注册上限/下限正确 |
| 登录/首页/返回/退出 | 通过 | 隔离合成账号经真实浏览器登录，实点三个功能入口及返回；POST 退出后回登录，返回封面可用 |
| 注册输入与眼睛 | 通过 | 自动化覆盖 10/11 字符、7/8 位、旧长用户名和邀请；登录/注册三个眼睛实点显示，1100ms 后恢复 password；390 宽度注册页无横向溢出 |
| 库存网页闭环 | 通过 | 合成番茄 3 个录入，实际使用 1 个后剩 2 个、版本 1；刷新仍为 2 个，流水核对一致 |
| 菜谱匹配与搜索 | 通过 | 合格番茄库存显示匹配条目，本地番茄炒蛋详细材料/器材/教程可读；空搜索提示且不跳转，输入后到独立结果页，返回可用；未点击外站链接 |
| 采购网页闭环 | 通过 | 合成土豆 2 个加入清单→买到了；此时仍只有 1 个批次/2 条流水；确认入库后 2 个批次/3 条流水/5 个动作，刷新不重复；两个批次合计 4000 千分量与流水总和一致 |
| 真实 YOLO 烟测 | 通过 | 在生产模型配置下加载真实 ONNX 并推理合成白色 JPEG，engine=yolo、uncertain=true、无候选；冷加载加推理 1.790 秒，不写库存。此项不代表真实食品准确率 |
| 生成服务未启用时的降级 | 自动化通过 | 生产 recipe_provider=off；本地工作台和已存教程正常。真实菜谱模型联调未执行；供应商/任务测试中的 mock 明确属于自动化 |
| 生产数据完整性 | 通过 | 只读核对 10 张账号/业务表与本轮优化前私有备份逐行相同；完整性 ok，外键问题 0；BVT 写入仅发生在独立合成库 |
| 恢复前局域网 HTTPS/真实手机 | 当时阻塞 / 未执行 | 原构建 BVT 时 Caddy Stopped、8443 无监听；后来服务恢复与 Android 现场结果见上方补测，不将警告当通过 |

环境实测：Python 3.10.20、Django 5.2.17、Python SQLite 运行库 3.53.2，Windows；生产主机和隔离浏览器均在本机。此轮不是性能压测、漏洞扫描、真实 Mac/Android 或阶段 08 完整验收。

## 发现与修复

- 教程搜索结果页的返回文字还写“返回做什么”；改为“返回查看菜谱”，路由不变，浏览器重启服务后重新加载并实点返回通过。
- 家庭邀请码提示还写“登录首页的注册页面”；改为“封面的注册页面”，与当前四层导航一致，邀请码、签名和注册权限没有修改。
- 修复后 `tests.test_page_adjustments` 与 `tests.test_second_optimization` 共 **10 项，1.454 秒，退出码 0**。只改两处文本，没有新增功能或数据库迁移；完整 113 项是修复前基线的实际运行结果，没有把它说成修复后再次全量执行。
- 按既有停止脚本等待 8000 清空后重启生产 Waitress，使模板缓存更新；再次最小运行检查通过。临时 8766 测试服务与本轮浏览器标签在测试后关闭。

## 执行入口与数据隔离

在现有项目的 PowerShell 中：

```powershell
& .\.venv\Scripts\python.exe manage.py test tests --settings=config.settings.test --noinput
& .\.venv\Scripts\python.exe -m pip check
& .\scripts\manage_prod.ps1 check --deploy
& .\scripts\manage_prod.ps1 migrate --check
& .\scripts\manage_prod.ps1 makemigrations --check --dry-run
```

测试 runner 创建/销毁 work/test_file.sqlite3，含真实文件数据库多连接测试；不接触生产库。浏览器使用 work/second_optimization_ui_settings.py、work/second-optimization-ui/app.sqlite3 和 127.0.0.1:8766，仅合成账号、番茄和土豆。生产诊断仅 GET、静态文件核对、模型推理与数据库只读比较；没有用真实账号登录、发真实采购或扣真实库存。运行配置、真实库、照片、Cookie、CA 私钥和日志没有加入仓库。

实际采购页面截图保存在本机 outputs/bvt-20261004-shopping.png；显示的是合成数据，不是手机现场记录。

## 后续门禁

Caddy 与电脑端严格 HTTPS 检查已恢复。Android 使用者须按 HANDOFF.md 核对并信任公开 CA，无警告打开健康页后，再验收登录、静态资源和手机采购闭环；未完成前保留发布阻塞。真实菜谱生成模型联调与真实设备相机测试仍单列待办。下一步反馈：健康页无证书警告并显示 ok。
