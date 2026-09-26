# 食尽其用实施进度

## 阶段 01：环境、骨架与可信 HTTPS（2026-09-25）

**状态：**本机骨架、迁移、Caddy HTTPS 反向代理与 loopback Waitress 已运行并通过本机检查。真实手机在新 Django 页面上的无警告访问、以及另一设备不能直连 8000，仍待现场反馈；不得据此宣称应用已上线验收。

### 已实现及变更文件

- 从规格包原样复制并校验根 `AGENTS.md`、`docs/ARCHITECTURE.md`、`docs/SOURCES.md`；当前目录原先没有应用代码或 Git 仓库，未覆盖用户文件。
- 建立 `.venv`、`requirements.lock`、`.gitignore`、`.env.example`、`README.md`；依赖精确版本见锁文件。
- 建立 `config/settings/{base,dev,prod,test}.py`、`core`、`inventory`、`meals`、`shopping`、`templates`、`static`、`scripts`、`tests`；后 3 个业务 app 目前仅为空骨架。
- `config/urls.py`、`core/views.py`、`core/middleware.py`：中文无数据占位页、最小健康接口、CSP/Permissions-Policy/no-store。
- `scripts/initialize_runtime.ps1` 仅首次生成随机密钥和私有 `data/runtime.env`；`scripts/load_runtime.ps1`、`manage_prod.ps1`、`start_waitress.ps1`、`serve_waitress.py` 实现生产启动与 127.0.0.1:8000 的 4 线程 Waitress。
- `config/Caddyfile` 使 Caddy 在用户指定的 `8443` 提供内部 CA HTTPS，仅将应用请求代理到 Waitress，仅从独立静态目录提供 `/static/`。Caddy Windows 服务身份固定为 `NT AUTHORITY\LocalService`，CA 保存在 `C:\ProgramData\ShiJinQiYong\CaddyData`。手机此前使用的根 CA 已保留；公开根证书导出到 `outputs/shijinqiyong-root.crt`，没有导出私钥。
- `docs/API.md`、`docs/ENVIRONMENT.md` 记录接口、实测环境与限制。`tests/test_stage01.py` 覆盖最小健康响应、占位页安全头和未开放 admin。

### 接口与迁移

- `GET /`：无真实家庭数据的中文占位页。
- `GET /health/`：仅 `{"status":"ok"}`；非 GET 返回 405。
- `/static/`：Caddy 读取独立 `staticroot`，生产模板使用指纹 CSS。
- 已在本机 `data/app.sqlite3` 执行 Django 自带 `contenttypes`、`auth`、`sessions` 迁移；没有创建家庭成员或业务记录。SQLite 当前 `journal_mode=delete`，尚未启用 WAL。

### 实际执行与结果

| 检查 | 实际结果 |
|---|---|
| 虚拟环境安装 Django 5.2.17、Waitress 3.0.2、argon2-cffi 25.1.0 | 退出码 0；虚拟环境实际 SQLite 3.53.2 |
| `scripts/manage_prod.ps1 check` | 退出码 0；0 个问题 |
| `scripts/manage_prod.ps1 migrate --noinput` | 退出码 0；auth/contenttypes/sessions 迁移成功 |
| `scripts/manage_prod.ps1 collectstatic --noinput` | 退出码 0；1 个静态源文件及指纹版本生成到独立目录 |
| `scripts/manage_prod.ps1 check --deploy` | 退出码 0；仅 `security.W004`（IP 访问时暂不启用 HSTS），未屏蔽警告 |
| `.venv/Scripts/python.exe -m pip check` | 退出码 0；没有依赖冲突 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 退出码 0；3 个测试全部通过 |
| Caddy 配置验证 | 退出码 0；配置有效；两条显式代理头覆盖被 Caddy 提示为与默认行为重复，已核对官方说明 |
| 本机可信 HTTPS 请求 | 使用导出的根证书，未关闭验证；`/`、`/health/`、指纹 CSS 均返回 200；动态响应 no-store，首页有 CSP |
| 直接 loopback HTTP | 对 `127.0.0.1:8000` 的请求返回 301 到 HTTPS；8000 实际仅监听 `127.0.0.1` |
| 代理头测试 | 本机临时 Caddy + Waitress 测试进程发送伪造 `X-Forwarded-For=203.0.113.45` 与 `X-Forwarded-Proto=https`；Django 请求对象实际 `REMOTE_ADDR=127.0.0.1`、`is_secure=False`；进程已停止 |
| Caddy 服务与防火墙 | 服务状态 Running、身份 LocalService；仅监听 `192.168.1.127:8443`；入站规则限定 WLAN、Caddy 程序、本机地址和 `192.168.1.0/24` |

安装 Caddy 服务时曾因复制证书文件的 ACL 缺失而启动失败，已修正每个文件对 LocalService 的权限并重新启动。Waitress 首次脚本导入路径错误，改为模块启动后重新验证。配置验证意外生成的未使用 CA 和旧测试 CA 副本已清理，保留的正式 CA 与手机测试时的公开根证书相同。

### 未完成、人工步骤与风险

- **待人工验证：**手机打开新 `https://192.168.1.127:8443/` 是否显示「食尽其用」占位页且无证书警告；另一设备访问 `http://192.168.1.127:8000/` 是否无法连接。用户此前确认手机能访问旧连通性测试页，不能替代这两项新验证。
- **未执行：**真实家庭业务流程、登录/权限、并发库存、备份恢复、主机重启恢复、真实性能测量、漏洞扫描和公网映射核查。阶段 02 加入登录与权限，后续阶段逐项验证。
- Caddy 服务当前为手动启动；Waitress 由当前用户会话运行，关闭会话或重启主机后不能视为已恢复。正式托管与重启验收留在运维阶段。
- Windows WLAN 当前为 Public，防火墙规则只匹配当前地址与网段；变化后必须复核。`80/443` 仍由 Steam++.Accelerator 占用，未改动。用户已明确允许使用 `8443`，相应访问地址包含端口。
- 阶段 01 公开的仅是无数据占位页与健康状态；业务页面和独立成员账号尚未加入，不能供家人记录真实食材。
- 当前目录无 Git 仓库。阶段 01 的可回退方案是仅打包代码与文档的 `outputs/stage01-source.zip`；`data/`、`work/`、`.venv/`、CA 私钥和日志均不纳入。

**下一阶段入口：**发送阶段 02 身份、权限与数据基础提示词。先复查本文件和手机现场结果，再建立独立成员账号、登录保护、CSRF 与登录节流。

## 阶段 02：身份、权限与数据基础（2026-09-25）

**状态：**本机迁移、认证/权限/节流与接口预留已完成；可信 HTTPS 入口仍运行。用户反馈手机可连接，但未明确新登录页是否无证书警告、另一设备能否访问 8000。没有创建真实成员，业务写入尚未开放。

### 已实现与变更文件

- `config/settings/base.py`、`config/urls.py`、`core/{views,middleware,security,models}.py`：Django 原生登录/退出、默认登录保护、显式 `MemberRole`（管理员/成员）、管理员设置访问控制、API 401/403、CSRF 失败结构化错误、会话 8 小时、64 KiB 上传内存上限。
- `core/management/commands/manage_member.py`：本机交互创建、改密、禁用/启用和指定账号/IP 解锁；密码经 Django 验证且不回显。禁用或改密会撤销该用户数据库 session；没有默认账号或远程恢复路径。
- `requirements.lock`：新增固定版本 `django-axes==8.3.1`，配置数据库持久记录，按账号与真实来源 IP 分别统计，5 次失败后冷却 15 分钟。来源仅使用 Caddy 覆盖的单值代理头和可信 loopback；生产不开放 Django admin。
- `core/models.py`、`inventory/models.py`、`shopping/models.py` 与各自迁移：单家庭设置、标准食材和别名、分批库存、动作幂等键、流水、采购项及唯一入库结果字段。数据库约束覆盖合法状态、非负数量、流水余额等；尚无业务服务和可写页面。
- `templates/core/{login,index,locked,settings}.html`、`templates/{403,403_csrf,404,500}.html`、`static/css/app.css`：中文手机优先登录与占位页、外置 CSS、退出 POST 表单及脱敏错误页。
- `tests/test_stage01.py`、`tests/test_stage02.py`、`docs/API.md`、`docs/ENVIRONMENT.md`、`README.md`：更新测试、固定后续 API 路径/错误合同、交互管理命令和环境说明。

### 接口与迁移

- `GET/POST /login/`、`POST /logout/`、`GET /settings/`、`GET /api/settings/` 已接入；除登录/健康/静态外所有页面与 API 默认要求登录。普通成员不得读取管理员设置；无角色账号也被拒绝。
- 固定 `/api/inventory/`、`/api/inventory/{id}/`、`/api/actions/`、`/api/actions/{id}/`、`/api/today/`、`/api/recipes/`、`/api/shopping/`、`/api/shopping/{id}/receive/`、`/api/movements/` 路径。已认证请求目前返回 501 `not_implemented`，错误方法 405；未登录 401。**这不是已实现业务写入。**
- 先用 sqlite3 备份 API 创建私有 `data/backups/stage01-before-stage02.sqlite3`；备份完整性 `ok`。已执行 Axes 0001–0010、core 0001、inventory 0001、shopping 0001–0002 迁移。生产库迁移后完整性 `ok`，仍为 `journal_mode=delete`；0 账号、0 批次、0 购物项。演示账号只在测试库。

### 实际测试与结果

| 检查 | 实际结果 |
|---|---|
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 退出码 0；17 项通过。`Client(enforce_csrf_checks=True)` 覆盖持久登录、匿名 401、角色 403、登录/退出及预留写请求 CSRF、坏 Origin、注销/禁用/改密旧会话失效、Argon2 哈希、账号/IP 节流与解锁、代理 IP 解析、数据库约束和无路径错误页 |
| `scripts/manage_prod.ps1 check` | 退出码 0，0 个问题 |
| `scripts/manage_prod.ps1 migrate --noinput` | 退出码 0，以上迁移全部应用 |
| `scripts/manage_prod.ps1 collectstatic --noinput` | 退出码 0，更新 CSS 及指纹文件到独立静态目录 |
| `scripts/manage_prod.ps1 check --deploy` | 退出码 0，仅 `security.W004`：按 IP 访问暂不启用 HSTS；未屏蔽警告 |
| `.venv/Scripts/python.exe -m pip check` | 退出码 0，无依赖冲突 |
| 私有备份与生产库 `PRAGMA integrity_check` | 两者均 `ok`；数据目录、数据库与备份 ACL 实查只有当前用户、SYSTEM、Administrators |
| Caddy → Waitress 可信 HTTPS 本机探测 | 使用公开根证书校验、未禁用校验；`/` 302 到登录、`/login/` 200、`/health/` 200、匿名 `/api/inventory/` 401、指纹 CSS 200；坏 Origin/缺 CSRF 403、匿名写 API 401、70 KB 请求 413 |
| 服务监听 | Caddy 仍为 `192.168.1.127:8443`；重启后的 Waitress 仍仅为 `127.0.0.1:8000` |

开发中首次测试出现 6 项失败，原因是测试端 HTTPS POST 未模拟浏览器 Origin；改为真实 CSRF 请求后通过。后续发现 Axes 8.3.1 在当前配置下没有输出 `Retry-After`，未在接口合同承诺该头；15 分钟冷却与中文 429 页保留。禁用后重新启用可能恢复旧会话的问题由本机命令撤销会话解决并回归。收紧 `data/` ACL 时，首次操作意外移除文件访问规则，数据库短暂无法打开；已恢复当前用户、SYSTEM、管理员的显式权限，复核备份与生产库完整性后才执行迁移。没有删除或覆盖数据库。

### 未完成、人工步骤与风险

- **人工：**在本机用 `scripts/manage_prod.ps1 manage_member create <用户名> --role admin` 交互创建首位管理员；密码不会回显。再按需创建成员。用户用手机访问 `https://192.168.1.127:8443/login/`，核对无证书警告并测试登录/退出；另一设备试连 `http://192.168.1.127:8000/` 应无法连接。账号未创建前不能验证真实手机登录。
- **未执行：**真实手机新登录页与真实成员会话、双设备访问限制、账号锁定冷却的时钟推进测试、主机重启恢复、备份恢复、真实业务写入/并发和性能测量。阶段 01 的临时 Caddy 代理头防伪测试与本阶段来源解析测试已完成；仍需用真实多设备确认日志中的 IP 区分。
- 业务模型只提供表与约束；输入十进制转换、业务事务、版本条件更新、持久幂等结果及流水联动留给阶段 03。不要用目前 501 路径记录真实食材。
- Waitress 仍依赖当前用户会话；Caddy 服务为手动启动。HSTS 仍因 IP 地址按架构暂缓。网络地址变化需复核 Host、Origin、Caddy 与防火墙。登录失败记录含账号/IP，留在私有数据库且不加入交付。
- 无 Git 仓库；阶段 02 源码与文档的可回退包为 `outputs/stage02-source.zip`，不含 `.venv/`、`data/`、`work/`、`outputs/`、静态收集目录、数据库、密钥或日志。迁移前数据库备份只在私有 `data/backups/`，恢复必须在停止写入后按后续运维流程进行，不能直接覆盖正在运行的数据库。

**下一阶段入口：**发送 `03_INVENTORY.md`（阶段 03：库存核心、事务与幂等）。先审查本阶段账号与手机反馈，再实现批次写入、流水、版本检查与真实多连接 SQLite 测试。

## 阶段 03：库存、精确数量、幂等与并发闭环（2026-09-25）

**状态：**库存批次、网页表单、同源 JSON API、动作流水与并发保护已在本机实现并通过自动测试。用户在开始本阶段前反馈手机测试成功；阶段 03 新页面尚未收到真实手机录入/扣减反馈。今日优先项、菜谱和采购留待对应阶段。

### 已实现与变更文件

- `inventory/services.py`：新增批次、分页查询、非数量编辑、做饭用量、直接食用、真实丢弃、库存校正和零余额归档。数量仅接受最多三位小数的十进制字符串，存为千分之一整数；单位由用户显式提交，不猜测换算。疑似变质、储存待核对或包装日期已过的批次不可登记为做饭/直接食用；计划日期不作安全期限。
- `inventory/models.py`、`inventory/migrations/0002_remove_businessaction_action_kind_valid_and_more.py`：动作种类扩展到做饭/直接食用/校正，数量上界和余额约束进入数据库。新增时写入库流水，校正写正负校正流水，丢弃单独标记；普通编辑不改数量、单位或食材标识。
- 所有库存写入在短 `transaction.atomic` 中先核对持久幂等结果，再用版本号、数量和状态条件更新，原子提交库存、动作结果和流水。一项失败整体回滚；相同操作者/编号/规范化参数重放原结果，不同参数 409。仅确认的 SQLite 忙返回 503 和 `Retry-After: 2`，其他数据库故障不伪装为忙。
- `inventory/api.py`、`inventory/views.py`、`config/urls.py`：普通表单和 JSON API 复用同一业务服务；登录、角色、会话和 CSRF 仍由 Django 控制。新增 `/inventory/`、`/inventory/{id}/edit/`、`/inventory/action/` 页面及 `/api/inventory/`、`/api/inventory/{id}/`、`/api/actions/`、`/api/actions/{id}/`、`/api/movements/` 接口；后续今日/菜谱/采购 API 仍为 501。
- `templates/inventory/{list,edit,error}.html`、`templates/core/index.html`、`static/css/app.css`、`static/js/inventory.js`：手机优先录入、浏览、编辑和动作表单。写入期间显示提交中；网络或服务器结果不确定时显示“结果待核对”，在当前页面保留原请求编号和原参数供重试。动态家庭页不缓存，用户文本经过模板转义或 `textContent`。
- `config/Caddyfile`：源配置改为只允许 12 位指纹静态文件长期缓存，其他静态文件保持 `no-store`；当前运行的管理员保护配置尚未应用此变更，见下方限制。
- `tests/test_stage03.py`、`tests/test_stage02.py`、`config/settings/test.py`：新增 19 项阶段 03 测试，调整阶段 02 对已开放路径的预期；并发测试使用真实文件数据库。`docs/API.md`、`docs/ENVIRONMENT.md`、`README.md` 同步接口、运行说明和环境限制。

### 迁移与实际测试

| 检查 | 实际结果 |
|---|---|
| 迁移前私有备份 `data/backups/stage02-before-stage03.sqlite3` | 使用 Python sqlite3 备份 API；`integrity_check=ok`，未覆盖原库 |
| `scripts/manage_prod.ps1 migrate --noinput` | 退出码 0；已应用库存 0002 迁移 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 退出码 0；36 项通过，其中阶段 03 新增 19 项。覆盖 3 个番茄扣 1 和 0.5、0.1/0.2 精度、非法值、幂等重放/异参 409、多批次回滚、重复批次、单位冲突、旧版本、校正流水、不可用状态、表单/API/CSRF、HTML 转义、分页、两成员争最后一份、同键并发和独立连接锁忙 |
| 合成文件库跨进程读写 | 两次独立 Python 进程命令均退出码 0；写进程提交 3 个合成番茄并扣 1.5，读进程核对剩余 1.5、2 条动作及流水总和 1.5 |
| `scripts/manage_prod.ps1 makemigrations --check --dry-run` | 退出码 0；无未生成迁移 |
| `scripts/manage_prod.ps1 check --deploy` | 退出码 0；仅 `security.W004`（局域网 IP 暂不启用 HSTS），未屏蔽警告 |
| `.venv/Scripts/python.exe -m pip check` | 退出码 0；无依赖冲突 |
| `node --check static/js/inventory.js` | 退出码 0；仅本机语法检查，运行时不依赖 Node |
| `scripts/manage_prod.ps1 collectstatic --noinput` | 退出码 0；已收集最新 CSS/JS 及指纹文件 |
| 生产库 `PRAGMA integrity_check` 与只读计数 | 退出码 0；完整性 `ok`，`journal_mode=delete`；2 账号、0 批次、0 动作、0 流水，未向生产库导入演示数据 |
| 重启 Waitress 后本机可信 HTTPS 探测 | 使用导出的公开根 CA 验证、未关闭校验；`/health/` 200、匿名 `/inventory/` 302、匿名库存/流水 API 401、指纹 JS 200、匿名写 API 401；Caddy 与 8443 防火墙设置未改 |
| `caddy adapt --config config/Caddyfile --adapter caddyfile --pretty` | 退出码 0；新静态缓存规则可解析。完整 `adapt --validate` 在非提升会话退出码 1，原因是现有私有 CA 目录拒绝读取；尚未执行管理员部署 |
| `work/stage03_snapshot.py` | 首次因未跳过 `__pycache__` 退出码 1；修正后退出码 0，源码快照 84 个文件，ZIP CRC 检查无坏项，包含进度、业务服务和新迁移 |

开发中首次锁忙测试暴露当前 Python sqlite3 没有导出预期的错误码常量/属性；按明确的 SQLite 忙/锁错误码或消息识别并重跑通过。独立合成库探测首次因脚本导入路径失败，修正后两个进程都成功。阶段 02 两项测试曾因库存路径从 501 正式开放而失败，更新对应状态预期后完整套件通过；未删除断言或跳过业务检查。

最终 HTTPS 探测脚本首次误用应用虚拟环境执行，因该环境没有测试专用 `httpx` 而退出码 1；改用本机已有 `httpx` 的 Python 后退出码 0，没有向应用锁文件增加运行依赖。探测显示指纹 JS 当前也是 `no-store`，据此修正仓库 Caddy 源配置；现运行配置仍需管理员应用。

### 未完成、人工步骤与风险

- **手机验收：**用已有成员账号访问 `https://192.168.1.127:8443/inventory/`，录入一个真实批次，核对列表数量；记录一次实际使用、丢弃或校正，刷新后核对余额与流水。若出现“结果待核对”，先保留页面并用原请求编号重试；不要以新的编号重复扣减。请反馈页面、证书警告、登录状态及操作结果。包装日期和储存状况应如实填写；不能用应用结果代替食物安全判断。
- **未执行：**阶段 03 新页面的真实手机触控/响应时间测试、Windows 服务或主机重启后的自动恢复、生产库备份恢复演练、真实家庭数据的使用闭环、性能测量、漏洞扫描和公网映射核查。本机 HTTPS 探测不等于手机验收；跨进程合成库验证不等于服务重启验证。
- 生产库存当前为空，两个成员账号存在；不要导入合成数据或覆盖真实成员。前端仅在当前页面内保留不确定请求，刷新会失去该内存状态；持久动作结果可由 API 查，但页面没有跨刷新自动恢复功能，也没有离线写队列。
- Caddy 服务为手动启动，Waitress 依赖当前用户会话；局域网地址变更需复核证书、Host/Origin、Caddy 和防火墙。当前数据库保持 SQLite DELETE 日志模式。`security.W004` 仍按当前 IP HTTPS 架构暂缓，不作为无警告部署结论。
- **待管理员应用：**为启用指纹静态文件长期缓存，在管理员 PowerShell 备份 `C:\ProgramData\ShiJinQiYong\Caddyfile`，复制仓库已验证语法的 `config/Caddyfile`，验证后重启 Caddy，再用可信根证书核对指纹 JS 的 `Cache-Control`。此前实际响应为 `no-store`；此项不影响库存写入，但尚不满足预期缓存策略。不要绕过私有 CA 文件权限或关闭证书验证。
- 当前目录无 Git 仓库；阶段 03 源码与文档可回退包 `outputs/stage03-source.zip` 只收录明确列出的代码、模板、静态源文件和文档，排除 `.venv/`、`data/`、`work/`、`outputs/`、收集后的静态目录、数据库、密钥和日志。私有迁移前备份保存在 `data/backups/`，恢复前必须停止写入并按运维步骤执行，不能直接覆盖运行中的数据库。

**下一阶段入口：**手机确认阶段 03 的新库存操作后，发送 `04_MOBILE_TODAY.md`（阶段 04：手机首页与今日优先项）。下一阶段读取库存状态并给出优先顺序，继续排除疑似变质、包装日期已过和储存待核对的批次。

## 阶段 04：手机首页、局部更新与今天先吃（2026-09-25）

**状态：**真实库存驱动的“今天先吃”首屏、手机四入口、搜索和局部列表更新已实现；生产迁移、静态收集、Caddy 静态缓存/压缩与 Waitress 恢复已完成。用户在开始本阶段时反馈上一阶段“已经测试”，没有提供逐项手机验收数据。本阶段页面只在本机独立合成库浏览器中验证，仍待真实手机核对。

### 已实现与变更文件

- `inventory/models.py`、`inventory/migrations/0003_inventorylot_manual_priority.py`：批次增加默认关闭的 `manual_priority`。现有库存会保留并默认普通排序；字段经新增/编辑服务验证，编辑受原版本号、幂等与事务约束。
- `inventory/services.py`、`inventory/today.py`：库存读接口增加最多 80 字的名称搜索，分页仍默认 50、最多 100；批次输出增加中文单位/状态标签及更新时间。今日服务按已配置家庭时区（无家庭设置行时用运行配置）计算今天，只从当前真实在库批次产生“先安排”和“需要核对”，各显示前 3 批及总数。先排除疑似变质、储存待核对、包装日期已过，再按手动优先、计划日期、入库时间、ID 排序；无计划日期排后，包装日期“不适用”不等于储存未知。逾期计划只称“计划已过”。
- `core/views.py`、`config/urls.py`、`inventory/api.py`：`/` 与 `/api/today/` 开放今日读取；`/recipes/`、`/shopping/` 明确显示未开放占位，相关 API 仍为 501；`GET /api/actions/by-request/{uuid}/` 允许原操作者按持久请求编号查询结果，未提交/非本人返回 404。
- `templates/core/{index,nav,placeholder}.html`、`templates/inventory/{list,edit,error}.html`、`static/css/app.css`：服务器首屏、底部今天/冰箱/做什么/采购四入口、44 像素以上主要控件、可见键盘焦点、长中文换行、空库 5 样引导、搜索与日期来源、手动优先编辑。普通表单无 JavaScript 仍能录入和更正；页面没有内联脚本、远程资源或虚构菜谱/采购数据。
- `static/js/{today,inventory}.js`：外置原生模块手动刷新今日、250 毫秒防抖搜索、取消并忽略过期读取、局部重绘当前列表，用户文本只写 `textContent`。写请求显示 pending/success/error/unknown；超时或断连先按原请求编号查询已提交结果，查不到则保留原参数供重试，不把 `AbortController` 当作服务器取消。成功后才清空新批次表单并生成下一个请求编号。无离线写队列。
- `config/Caddyfile`：静态路由增加 `zstd/gzip` 编码，并保留仅指纹文件长期缓存的规则；已通过管理员提升备份、验证并应用到运行服务。`tests/test_stage04.py` 新增 7 项服务端回归；`docs/API.md`、`docs/ENVIRONMENT.md`、`README.md` 更新。

### 接口、迁移与实际测试

| 检查 | 实际结果 |
|---|---|
| 迁移前私有 `sqlite3.backup` | 退出码 0；`data/backups/stage03-before-stage04.sqlite3` 完整性 `ok`，未覆盖生产库 |
| `scripts/manage_prod.ps1 makemigrations inventory`、`migrate --noinput` | 均退出码 0；生成并应用库存 0003 手动优先迁移 |
| `.venv/Scripts/python.exe manage.py test tests.test_stage04 --settings=config.settings.test` | 首次退出码 1：占位文案与 UUID 路由参数测试发现 2 处问题；修正后退出码 0，7 项通过 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 退出码 0；43 项通过，包括原库存多连接并发、幂等和本阶段排序、排除、时区、搜索转义、无 JS 表单、动作查询权限 |
| `scripts/manage_prod.ps1 makemigrations --check --dry-run` | 退出码 0，无未生成迁移 |
| `scripts/manage_prod.ps1 check --deploy` | 退出码 0；仅 `security.W004`（局域网 IP 暂不启用 HSTS），未屏蔽警告 |
| `node --check static/js/inventory.js`、`node --check static/js/today.js` | 均退出码 0；Node 只用于语法检查，不是应用运行依赖 |
| `caddy adapt --config config/Caddyfile --adapter caddyfile --pretty` | 退出码 0；源码配置语法可解析，仍提示两条现有代理头设置与默认行为重复 |
| `scripts/manage_prod.ps1 collectstatic --noinput`、`.venv/Scripts/python.exe -m pip check` | 均退出码 0；3 个静态文件复制并生成指纹版本，无依赖冲突 |
| 生产库只读检查 | 退出码 0；`integrity_check=ok`、`journal_mode=delete`，2 个现有成员账号、0 个批次，新增列存在；没有导入合成食材 |
| 管理员 Caddy 应用脚本与可信 HTTPS 复核 | 脚本解析退出码 0；管理员进程写入 `status=applied`，私有备份为 `Caddyfile.stage04-20260925-143749.bak`，Caddy 服务仍 Running。使用公开根 CA 校验、没有关闭校验；指纹 CSS/两个 JS 均 200，`Cache-Control: public, max-age=31536000, immutable`，请求 `Accept-Encoding: gzip` 时均返回 `Content-Encoding: gzip`；非指纹 CSS 仍为 `no-store`；`/health/` 200、匿名 `/` 302、匿名今日 API 401，动态响应 `no-store` |
| 独立合成库浏览器 | 390 CSS 像素首页/库存截图已保存；360、390、430 像素无横向溢出；底部入口 48、操作按钮 44 CSS 像素；搜索“番茄”局部缩为 2 批；实际扣 0.5 后列表为 1.5、版本 1，快速双击扣 0.1 后为 1.4、版本 2 且该批次总流水仅 3 条（含入库）；断线提交保留 0.2 输入、提示结果待核对，余额不变；退出后后退到登录页。浏览器脚本错误列表为空 |
| 合成库 loopback 无缓存原始响应体 | 首页 HTML+CSS+JS 10,815 字节；库存页 27,815 字节。此项不是手机 Wi-Fi 或生产 Caddy 压缩后的性能数字 |
| `work/stage04_snapshot.py` 与 ZIP 校验 | 退出码 0；源码快照 90 个文件，CRC 无坏项，包含今日服务和库存 0003 迁移；未包含数据库、私钥、日志或测试工作目录 |

浏览器使用 `work/stage04-browser-data/app.sqlite3` 独立测试库和只绑定 `127.0.0.1:8765` 的开发进程；进程测试后已停止。浏览器仅生成合成数据截图，不展示真实家庭记录。首次全页截图工具无法捕获，改用真实浏览器视口截图保存；未伪称全页截图。生产 Waitress 重启后，首次核对脚本误以为虚拟环境启动器 PID 应等于监听 PID，退出码 1；随后核实监听进程是该启动器的子进程。管理员重启 Caddy 后的第一次动态 HTTPS 探测返回 502，发现 Waitress 已停止监听；改为在持续的本机终端会话运行启动脚本后，健康、匿名授权和指纹静态资源重新通过可信 HTTPS 探测。该会话仍是可用性的限制，不能宣称服务重启恢复已验收。一次只读数据库探测命令因右括号缺失失败，修正后退出码 0。

### 未完成、人工步骤与风险

- **手机验收：**打开 `https://192.168.1.127:8443/`，确认无证书警告、四入口、今日两组与实际库存一致；若库存为空，应显示 5 样引导而不是虚构推荐。录入或编辑“手动优先”，刷新今日核对顺序；在冰箱页搜索长名称，并试一次真实操作。请反馈手机浏览器、宽度、是否横向滚动和具体错误；不要发送密码、Cookie 或真实数据库。
- **运行限制：**指纹静态缓存与 gzip 已在当前 Caddy 服务实际生效；动态请求依赖当前持续运行的 Waitress 终端会话。关闭该会话或主机重启后的自动恢复尚未配置/验收，测试前需要确认 `127.0.0.1:8000` 监听与 `/health/` 返回 200。Caddy 源配置备份留在私有 ProgramData，不在交付包内。
- **未执行：**真实手机 LCP/INP/CLS、家庭 Wi-Fi 冷缓存传输、浏览器慢网/403/409/503 的完整 UI 模拟、主机重启恢复、生产备份恢复、真实家庭业务闭环与公网映射核查。服务端 403/409/503 回归来自阶段 02/03，不能冒充本阶段真实手机测试。写入成功后另一设备仍需手动刷新才能看最新服务器记录；不做每秒轮询或离线写。
- 当前目录无 Git 仓库；可回退包 `outputs/stage04-source.zip` 只收录明确列出的源码与文档，不含 `.venv/`、`data/`、`work/`、`outputs/`、收集后的静态目录、数据库、密钥或日志。生产迁移前备份仅在私有 `data/backups/`，恢复时必须先停止写入，不能直接覆盖运行中的数据库。

**下一阶段入口：**阶段 04 手机反馈后发送 `05_RECIPES.md`。下一阶段只从当前可用批次匹配本地菜谱，并在用户确认实际用量时复用库存事务服务。

## 阶段 04 补充：简化录入与本机拍照识别（2026-09-25）

**状态：**用户反馈阶段 04 手机测试通过，并要求散装食材与包装文字都能拍照识别，同时减少平时录入字段。已实现本机识别建议和简化表单；真实手机拍照准确性尚待用户验收。

### 已实现与变更

- `templates/inventory/list.html`、`static/css/app.css`、`static/js/inventory.js`：新增手机拍照/选图入口；前端先缩图转 JPEG，识别后只填食材名称并提示核对，不自动入库。日常可见名称、实际数量、单位、位置、食材与储存状态；批次名、日期和手动优先折叠在“更多信息”。无 JavaScript 时仍保留手工普通表单。
- `inventory/recognition.py`、`inventory/api.py`、`config/urls.py`：新增 `POST /api/inventory/recognize/`，沿用 Django 登录、角色、会话、CSRF；只向 loopback Ollama `qwen3-vl:8b` 发送重新编码、去元数据的图片，不存原图、不写库存。支持 JPEG/PNG/WebP，输入限制 2.5 MB 原图和 2,000 万像素，一次返回一个名称建议；模型输出再次校验。模糊或失败时可手工录入。模型的 JSON 实测可能出现在 `thinking` 字段，已兼容只解析完整 JSON 的情况。
- `config/Caddyfile`、`config/settings/base.py`、`scripts/serve_waitress.py`、`core/middleware.py`：仅识别路径允许 4 MB 请求体，其余 Caddy 路径仍为 64 KB；Waitress 总上限 4 MB，Django 内存请求上限约 4 MB。摄像头权限策略限定同源，麦克风/定位禁用。无新 LAN 端口。
- `requirements.lock`：锁定新增 Pillow 12.3.0。`tests/test_photo_entry.py` 覆盖未登录/CSRF、无库存写入、图像拒绝、模型异常返回、最小普通表单与待核对批次排除。`docs/ARCHITECTURE.md` 追加用户明确变更，`docs/API.md`、`docs/SOURCES.md`、`docs/ENVIRONMENT.md`、`README.md` 更新。
- **数据库迁移：无。**原事务、版本、幂等和流水服务不变，只有用户最终点“保存批次”才写入。

### 实际执行与结果

| 检查 | 结果 |
|---|---|
| `pip install Pillow==12.3.0`、`.venv/Scripts/python.exe -m pip check` | 退出码 0；本机虚拟环境已安装，依赖检查无冲突 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 最终退出码 0；46 项通过。首次新增测试中有非 ASCII bytes 字面量语法错误，已修正并重跑；没有删断言或跳过测试 |
| `node --check static/js/inventory.js` | 退出码 0；仅语法检查，Node 非运行依赖 |
| `scripts/manage_prod.ps1 check --deploy`、`makemigrations --check --dry-run` | 均退出码 0；仅既有 HSTS/IP 的 `security.W004` 警告，无模型迁移变化 |
| Caddy `adapt` 与 `collectstatic` | 退出码 0；新 Caddy 路由语法可解析；2 个静态文件复制、3 个指纹文件后处理 |
| 本机已安装模型合成图推理 | 带“新鲜番茄”文字的示意图与去字番茄示意图均返回 `番茄`；暖态该示意图请求约 2 秒。此为合成图，不是现实照片准确率或手机延迟 |
| 可信 HTTPS 与路由限制 | 公开根 CA 验证下 `/health/` 200；70 KB 匿名识别请求 401（已通过 Caddy/Waitress 大小限制、身份门拒绝），70 KB 普通库存请求 413（Caddy）。本机 Ollama 仅监听 `127.0.0.1:11434`，Waitress 仅 `127.0.0.1:8000`，Caddy 仅 `192.168.1.127:8443` |
| 生产 SQLite 只读核对 | `PRAGMA integrity_check=ok`、0 批次；没有将合成照片、食材或测试账号加入生产库 |
| `work/photo_snapshot.py` | 退出码 0；`outputs/photo-entry-source.zip` 含 92 个源码/文档文件，ZIP CRC 无坏项，未含数据、私钥、日志或测试工作目录 |

管理员应用 Caddy 配置时，首次脚本将 Caddy 的正常 stderr 信息当作错误并自动恢复原配置；修正脚本后新配置已生效。服务管理器曾持续显示 `StartPending`，但可信 HTTPS 可用；核实进程路径后由管理员重启服务，目前为 `Running`。Caddy 使用原 `LocalService`、证书与 8443 防火墙规则，未创建新 CA。实际路由大小响应如上。Waitress 重启后由当前终端会话提供，仍无开机恢复保证。

最后一处前端修复防止识别返回时覆盖成员已经手动修改的名称，或覆盖已保存后重置的表单。之后 `node --check` 退出码 0、拍照录入 3 项针对性测试通过；重新 `collectstatic` 并重启 Waitress 后，可信 HTTPS 实际读取最新指纹文件 `js/inventory.19d37929b690.js` 为 200，包含拍照逻辑且缓存头为 `public, max-age=31536000, immutable`，`/health/` 为 200。源码快照已在该修复后重新生成并通过 CRC。

### 未完成与人工步骤

- **手机验收：**用现有成员账号打开 `https://192.168.1.127:8443/inventory/`，分别拍一件散装食材和一件有中文标签的包装；核对名称是否合理、是否能改名，再填写实际数量与单位、储存状况，保存后刷新列表。照片只建议一个主要名称；一张包含多种食材的照片未实现多项自动录入。
- **未执行：**真实手机相机/浏览器兼容性、不同真实食材照片识别准确率、冷启动模型耗时、断网状态、Ollama/Waitress/Caddy 的主机重启恢复、真实家庭库存写入。不得把合成图推理或本机 HTTPS 探测当成手机验收。
- 照片不能判断数量、包装日期、储存情况或食物是否安全；用户确认后才入库。储存默认“待核对”，不会进入可用推荐。Ollama 停止时识别返回 503，手工录入仍可用。Waitress 当前依赖终端，Ollama 也尚未配置开机恢复。
- 当前目录没有 Git；仅源码/文档快照作为回退方案，排除数据库、运行配置、私钥、照片、日志与测试工作目录。若要验证照片上传，请勿发送真实图片给外部服务。

**下一阶段入口：**请先反馈两类真实手机照片的识别与表单体验；随后继续阶段 05 的本地菜谱闭环，不引入在线 AI 或自动扣库存。

## 阶段 05：本地菜谱与实际用量确认（2026-09-25）

**状态：**已实现本地菜谱、真实可用批次匹配和确认实际用量后的库存扣减。用户本次指令为“开始阶段05”；仓库没有单独的 `05_RECIPES.md`，按 `docs/ARCHITECTURE.md` 的固定边界及上一阶段入口实施。真实手机上的新菜谱页面尚待用户验收。

### 已实现与变更

- `meals/data/recipes.json`、`meals/catalog.py`：提供 6 道本地家常菜及显式别名；加载时校验结构、长度、唯一性和别名冲突。没有自动生成用量、单位换算或在线模型请求。
- `inventory/availability.py`、`inventory/today.py`、`inventory/services.py`：今日推荐、菜谱匹配与做饭扣减共用家庭时区日期和可用性规则。疑似变质、储存待核对、数量为零或包装日期已过的批次不参与可用菜谱；服务端提交时再次核对。
- `meals/services.py`、`meals/views.py`、`config/urls.py`：开放菜谱列表、详情、确认提交和只读菜谱 API。选菜或看做法不写库存；提交必须给出菜谱所需每种食材的批次、真实用量及当前版本。服务端验证批次属于菜谱，再调用原 `apply_action(kind="cook")`，由同一事务执行版本检查、库存扣减、持久请求编号幂等与逐批流水。原编号原参数即使在批次用尽后重试也返回原动作。
- `templates/meals/{list,detail}.html`、`static/css/app.css`：手机优先的服务器渲染菜谱页和普通表单；不依赖 JavaScript 确认用量。页面明确“已找到”仅指名称匹配，不保证份量或食物安全。
- `tests/test_stage05.py`：覆盖别名与危险批次排除、只读不扣、登录/CSRF、实际扣减与耗尽后幂等重试、陈旧版本多批次回滚、非菜谱批次拒绝、包装过期、家庭时区边界。阶段 04 的菜谱占位预期更新为实际开放。`docs/API.md`、`README.md` 和设计记录同步更新。
- **数据库迁移：无。**实施前通过 SQLite 在线备份 API 建立私有 `data/backups/stage04-before-stage05.sqlite3`，完整性与外键检查通过；没有向生产库写入合成食材。

### 已执行检查

| 检查 | 实际结果 |
|---|---|
| `.venv/Scripts/python.exe manage.py test tests.test_stage05 --settings=config.settings.test` | 退出码 0，6 项通过 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 退出码 0，52 项通过 |
| `scripts/manage_prod.ps1 makemigrations --check --dry-run` | 退出码 0，无待生成迁移 |
| `scripts/manage_prod.ps1 check --deploy` | 退出码 0；仅既有 `security.W004`（当前 IP HTTPS 不启用 HSTS） |
| `.venv/Scripts/python.exe -m pip check` | 退出码 0，无依赖冲突 |
| 生产 SQLite 只读核对与私有阶段前备份 | `integrity_check=ok`；原库 2 个账号、0 个批次、0 个动作；备份经完整性与外键检查，不覆盖原库 |
| `scripts/manage_prod.ps1 collectstatic --noinput` 与 Waitress 重启 | 收集退出码 0，1 个静态文件复制、3 个文件生成指纹版本；Waitress 已在持续终端会话重新启动，Caddy 配置和防火墙未改 |
| 公开根 CA 验证的真实 HTTPS 探测 | `/health/` 200；匿名 `/recipes/` 302、匿名 `/api/recipes/` 401；新指纹 CSS 返回 200 与 `public, max-age=31536000, immutable`。未关闭证书校验；匿名探测不代表已登录手机流程 |
| `work/stage05_snapshot.py` | 退出码 0；`outputs/stage05-source.zip` 为 99 个源码/文档文件，ZIP CRC 无坏项，排除数据目录、运行配置、私钥、照片和日志 |

### 未完成与人工步骤

- **手机验收：**使用已有成员账号访问 `https://192.168.1.127:8443/recipes/`，查看列表与一道家常菜详情；若冰箱里有真实可用食材，按批次填本次**实际**用量并确认，再到冰箱核对余额和流水。仅打开菜谱不应扣库存。请反馈页面是否正常、菜谱匹配是否符合真实名称；不要发送密码、Cookie 或真实数据库。
- **未执行：**真实手机浏览与提交、家庭真实菜谱适配、主机重启后服务恢复、生产备份恢复演练和真实家庭全闭环。单机自动化测试不能替代手机验收。菜谱仅 6 道固定家常菜；别名只做明确列出的精确匹配，不能推断份量或食品安全。
- 当前 Waitress 与 Ollama 仍依赖现有会话，Caddy 服务保持原 LAN 端口、可信 CA 和防火墙范围。生产数据、私有备份、密码、Cookie、照片、CA 私钥与日志不进入源码交付包。采购入口尚未开放。

## 阶段 05 扩展：家庭菜谱、分类与教程收藏（2026-09-25）

**状态：**用户新增要求：根据现有食材排序并分类；家庭成员可保存自写菜谱，搜索并收藏视频、文字、图片教程；外部视频链接与本机视频上传两种方式都要，单个上传上限 200 MB。已实现并部署到原可信 LAN HTTPS 入口。真实手机的本阶段流程仍待用户验收。

### 已实现与变更文件

- `meals/data/recipes.json`、`meals/catalog.py`、`meals/services.py`：内置菜谱增加分类与标签；家庭菜谱与内置菜谱合并展示，按真实可用食材的匹配比例、匹配数排序，并支持分类及名称/食材/标签筛选。继续按家庭时区排除疑似变质、储存待核对、包装日期已过及零余额批次。已知别名显式归一，其他食材仅精确匹配。自建菜谱确认做饭仍委托原库存事务服务，不由菜谱页面直接改库存；菜谱编辑后，原做饭请求编号可幂等重试。
- `meals/models.py`、`meals/migrations/0001_initial.py`、`meals/forms.py`、`meals/views.py`、`config/urls.py`：新增家庭菜谱和私有附件表、创建/编辑页面、分类/标签/教程类型及 HTTPS 来源校验、版本检查与持久创建请求编号。单家庭成员共享内容，匿名和无家庭角色用户被原登录门拒绝。外部视频、文字、图片搜索仅在成员点击后由浏览器打开；应用不抓取网页、不自动下载或嵌入外站内容。
- `meals/media.py`、`templates/meals/{list,detail,form}.html`、`static/css/app.css`、`static/js/recipe-upload.js`：上传图片或 MP4/MOV/WebM 视频到静态目录之外的私有数据目录，经认证路由读取，视频支持单段 Range。图片最大 8 MiB/2,000 万像素并重编码去元数据；每菜最多 6 图、1 视频，视频 200 MiB。上传请求编号持久去重，客户端在超限时提前提示；服务器仍独立校验。普通表单在无 JavaScript 时仍能录入、上传与确认用量。
- `config/Caddyfile`、`scripts/serve_waitress.py`、`config/settings/base.py`：仅 `/recipes/family-*/upload/` 的 Caddy 请求体上限改为 220 MB；原照片识别仍为 4 MB，其余路由 64 KiB。Waitress 总上限相应为 220 MB，但仍只监听 loopback；Django 大文件临时目录在私有数据目录，单请求文件数受限。未改变防火墙、证书或局域网端口。
- `core/management/commands/backup_household.py`：备份命令要求 Waitress 停止，将 SQLite 和所有被数据库引用的附件一起复制到私有备份目录，并检查数据库、外键与附件 SHA-256。`tests/test_family_recipes.py` 覆盖权限、CSRF、重复创建/上传、分类排序与不安全批次、外链、菜谱版本、扣库存回放、图片重编码、私有媒体、Range 和含媒体备份。`README.md`、`docs/{ARCHITECTURE,API,SOURCES,ENVIRONMENT,PROGRESS}.md` 与设计记录更新。

### 迁移、部署与实际检查

| 检查 | 实际结果 |
|---|---|
| 实施前私有 `sqlite3.backup` | `data/backups/stage05-before-family-recipes.sqlite3` 建立并通过完整性、外键检查，未覆盖原库 |
| `scripts/manage_prod.ps1 makemigrations meals`、`migrate --noinput` | 均退出码 0；生成并应用 `meals.0001_initial` |
| `.venv/Scripts/python.exe manage.py test tests.test_family_recipes --settings=config.settings.test` | 最终退出码 0，5 项通过。开发中首次上传测试因过严要求 CSRF 必须在表单体内而失败，改为允许 Django 正常的 CSRF 头/表单方式后通过；备份测试发现 Windows 上 SQLite 连接未关闭导致目录重命名失败，显式关闭后通过 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 最终退出码 0，57 项通过，包括阶段 01–05 原回归 |
| `scripts/manage_prod.ps1 makemigrations --check --dry-run`、`check --deploy`、`pip check`、`node --check static/js/recipe-upload.js` | 均退出码 0；无待生成迁移和依赖冲突；部署检查仅既有 IP HTTPS 的 HSTS `security.W004` 警告 |
| Caddy 源配置 `adapt`、管理员应用与静态收集 | `adapt` 退出码 0；管理员配置备份、校验与应用成功，Caddy 服务仍 Running；`collectstatic` 退出码 0，2 个文件复制、4 个指纹资源后处理 |
| 可信 HTTPS 探测 | 公开根 CA 验证、未关闭校验；`/health/` 200，匿名菜谱/新增页 302，匿名菜谱 API 401，新指纹 CSS/JS 200 并长期缓存；70 KB 匿名上传路径 302、普通库存路径 413，证明路径上限区分已生效。匿名检查不代表已登录上传成功 |
| 外部搜索入口可达性 | 本机使用非家庭关键词分别请求必应文字、必应图片与 B 站搜索，三个 HTTPS 页面均返回 200；这不代表手机或未来始终可达，应用不会后台请求这些网站 |
| 生产库只读核对 | `integrity_check=ok`、外键错误 0；现有成员账号 2、真实批次 1、家庭菜谱 0、媒体 0；没有导入合成内容 |
| 生产数据只读菜谱服务检查 | 使用现有活跃家庭账号执行只读匹配，返回 6 道内置菜谱，退出码 0；没有输出家庭食材名称或修改记录 |
| `backup_household` 实际运行 | 停止 Waitress 后生成私有 `data/backups/household-20260925-163913-84e6e941/`，数据库及 0 个当前附件检查通过；Waitress 恢复后可信 HTTPS 健康 200。运行中再次调用按设计拒绝，退出码 1。合成库测试另验证 1 个媒体文件随库复制；实际恢复与异设备备份未执行 |
| `work/family_recipe_snapshot.py` | 退出码 0；`outputs/family-recipes-source.zip` 含 107 个源码/文档文件，ZIP CRC 无坏项，排除 `.venv/`、`data/`、`work/`、私有附件、数据库、密码配置、CA 私钥和日志 |

最后核对发现仅上传本机视频/图片时不应强制填外站链接：表单现允许先保存视频/图片菜谱，再在详情页上传文件；自写菜谱仍要求步骤，文字教程至少有步骤或 HTTPS 链接。补充断言后完整 57 项重跑退出码 0，Waitress 重启后可信 HTTPS 健康 200。该修改不涉及数据库迁移。

### 未完成与人工步骤

- **手机验收：**用已有成员账号打开 `https://192.168.1.127:8443/recipes/`，核对按当前冰箱食材排序与分类；新增一条家庭菜谱，填写标签和教程链接；可先上传一张自有图片与一个短 MP4（不必用满 200 MB），用另一家庭账号确认能查看，再退出确认未登录不能打开私有附件。实际做饭用量只在确认后扣除，并到冰箱核对流水。请反馈浏览器、页面/播放表现和具体错误，不发送密码、Cookie、真实数据库或 CA 私钥。
- **未执行：**真实手机视频上传与 Range 播放、200 MiB 边界上传、MOV/WebM 跨设备解码、外部搜索网站在用户网络中的可达性、从含真实媒体的生产备份恢复、异设备备份、主机重启恢复。外部来源可能失效；视频原文件未转码且可能保留拍摄元数据；目前的格式头测试不等于视频内容可播放。
- 生产 Waitress 仍由持续终端会话运行，关闭会话会使动态页面不可用。私有媒体与备份不得放入源码 ZIP 或静态目录。应用只支持一个家庭；若未来要多家庭，需另做数据隔离设计和迁移。采购入口仍未开放。

**下一阶段入口：**手机验收本扩展后，如继续完整产品闭环，请发送阶段 06 的采购要求或提示文件；需实现“避免买重”和“买到了才唯一入库”，保持原库存事务与流水约束。

## 阶段 06：采购与唯一入库（2026-09-25）

**状态：**按用户“开始阶段06”实施。当前仓库无独立阶段 06 提示文件，沿用 `AGENTS.md`、`docs/ARCHITECTURE.md` 与此前采购预留合同。功能已部署到原家庭 LAN HTTPS 入口；真实手机采购操作待用户验收。

### 已实现与变更

- `shopping/services.py`、`shopping/views.py`、`config/urls.py`、`templates/shopping/list.html`、`static/css/app.css`：成员可添加采购项、标记买到、取消、按实物数量唯一入库。页面显示可用库存汇总及最近完成项。添加同名食材时，在写事务内对照已记录批次和未完成采购项；成员核对后明确确认才可继续。已知别名精确归一，其他名称精确比较；跨单位不换算。疑似变质、储存待核对和包装日期已过的批次仅触发核对提醒，不进入可用库存汇总。
- `inventory/models.py`、`inventory/migrations/0004_remove_businessaction_action_kind_valid_and_more.py`：扩展采购动作种类及数据库约束。采购新增、买到、取消及入库动作共用成员 UUID 请求编号、参数摘要、持久结果与原动作记录；状态变更作版本条件更新。标记买到不改库存；实际入库在一个事务内写入新批次、正向库存流水和购物项一对一入库关联。相同请求编号回放原结果，不同编号也不能让同一购物项再次入库。新批次默认储存待核对。
- `tests/test_stage06.py`：覆盖同名/别名防买重、不安全批次排除、买到不入库、实际数量不同于计划、原编号幂等、换编号唯一入库、陈旧版本、取消、流水失败回滚、网页/接口权限和 CSRF，以及两条独立 SQLite 连接并发尝试入库。阶段 04 的采购占位断言改为实际清单。`docs/API.md`、`docs/ARCHITECTURE.md`、`README.md` 同步更新。原 `core/views.py` 中已无路由使用的采购占位处理已移除。

### 迁移与实际验证

| 检查 | 实际结果 |
|---|---|
| 生产迁移前私有备份 | 停止 Waitress 后执行 `backup_household`，生成 `data/backups/household-20260925-170707-66802f6b/`；工具完成 SQLite 完整性、外键及附件核对，当前引用附件 0 个；未覆盖原库 |
| `scripts/manage_prod.ps1 migrate --noinput` | 退出码 0，应用 `inventory.0004_remove_businessaction_action_kind_valid_and_more`；原 `shopping` 表无需新迁移 |
| `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` | 最终退出码 0，64 项通过；包含新增流水失败回滚断言与原阶段 01–05 回归 |
| `makemigrations --check --dry-run`、`check --deploy`、`pip check` | 退出码均为 0；无待生成迁移或依赖冲突；仅既有 IP HTTPS 不设置 HSTS 的 `security.W004` 警告 |
| `collectstatic --noinput` | 退出码 0；采购页面 CSS 的新指纹资源已收集，1 文件复制、4 个资源后处理 |
| 生产 SQLite 只读检查 | `integrity_check=ok`、外键错误 0、迁移已记录；原 2 个账号、1 个批次、1 个动作、1 条库存流水仍在；采购项 0。未写入测试采购项 |
| Waitress 恢复与可信 HTTPS | Waitress 恢复在持续终端会话，Caddy 仍在原 8443 端口；使用公开家庭根 CA 验证，`/health/` 200、匿名 `/shopping/` 302、匿名 `/api/shopping/` 401。未关闭证书校验；匿名探测不等于手机已登录验收 |
| `work/stage06_snapshot.py` | 退出码 0；`outputs/stage06-source.zip` 含 111 个源码/文档文件，ZIP CRC 无坏项，排除数据库、私有备份、运行配置、媒体、CA 私钥、日志和测试工作目录 |

本机 PowerShell 的默认 HTTPS 请求因未使用本项目公开根 CA 而失败，随后用显式根 CA 的 `httpx` 完成上述可信探测。一次只读 Django shell 命令因 PowerShell 引号传递失败，没有改数据库；改用 SQLite 只读 URI 成功核对。
最终代码收尾后再次运行完整 64 项测试，退出码 0；重新启动 Waitress 后可信 HTTPS 探测、生产库只读完整性与计数检查均退出码 0。Caddy 服务实际名称为 `ShiJinQiYongCaddy`，状态 `Running`；Waitress 只监听 `127.0.0.1:8000`，Caddy 只监听 `192.168.1.127:8443`。一次按通用名 `Caddy` 查询服务失败，改按实际服务名核实。

### 未完成与人工步骤

- **手机验收：**用已有家庭成员账号打开 `https://192.168.1.127:8443/shopping/`。先核对冰箱中已有食材的提示，添加一条确实要买的食材；标记“买到了”后确认冰箱库存未增加；实际放入冰箱时填写真实数量、位置和状态，点“确认入库”，再查看冰箱批次与流水。请使用真实家庭记录，不发送密码、Cookie、数据库或私钥。
- **未执行：**真实手机上的采购提交与双设备同时操作、异设备备份与真实恢复演练、主机重启后的 Waitress 自动恢复。应用不会根据菜谱自动推断应买数量，也不自动把不同单位相加；名称未在显式别名表时只精确比较。当前生产库没有采购项，所以生产环境仅验证匿名路由及数据库迁移，实际家庭写入仍待手机验收。
- Waitress 仍依赖持续终端会话；Caddy、证书、LAN 防火墙范围未改。生产数据、私有备份、媒体、密码、Cookie、CA 私钥与日志不进入源码交付包。

**下一阶段入口：**请先反馈手机采购闭环是否符合实际使用，再进行整体双设备验证、备份恢复演练和交接；按原时间纪律，停止新增扩展功能。

## 阶段 07：验证、运行可靠性与交接（2026-09-25）

**状态：**本机测试、私有备份和独立目录恢复演练已完成；当前家庭 WLAN 地址已按用户确认切换。用户随后确认手机能打开新地址，但提示证书不受信任，因此**手机可信 HTTPS 验收未通过，不能宣布内网上线完成**。用户此前也明确表示阶段 06 的手机采购流程“尚未测试或结果不确定”。本阶段停止新增产品功能。

### 代码、运行与文档变更

- `scripts/start_waitress.ps1`、`scripts/start_ollama.ps1` 增加有界重启循环；`scripts/register_logon_tasks.ps1` 注册当前用户登录任务，分别运行 Waitress 与本机 Ollama。`scripts/stop_waitress_for_backup.ps1` 在备份前停止登录任务并核对、关闭剩余的 Waitress 监听进程，拒绝关闭未知的 8000 端口进程。`scripts/initialize_runtime.ps1` 的首次配置默认 Host 与 Origin 更新为当前 WLAN 地址。
- `config/Caddyfile` 改为 `192.168.110.146:8443`，同时同步私有 `data/runtime.env` 的 Host/CSRF Origin。管理员提升后将 Caddy 配置与防火墙规则切换到新 WLAN 子网，并将 Caddy Windows 服务设为自动启动；保留原根 CA、LocalService 身份与 loopback 后端。私有配置分别留有备份，未输出密钥。
- `README.md`、`docs/ENVIRONMENT.md`、`docs/SOURCES.md` 和新建 `docs/HANDOFF.md` 更新当前入口、登录任务、备份/恢复、证书与手机验收说明。`work/stage07_*` 为不打包的核验脚本，`outputs/stage07-source.zip` 为仅源码和文档的交接包。
- 针对手机证书不受信，额外把原公开 PEM 根证书转换为 `outputs/shijinqiyong-root.cer`（DER，423 字节）；该文件的 SHA-256 与原证书的 DER 指纹一致。没有导出或改动 CA 私钥。`HANDOFF.md` 增加 iPhone/iPad 与 Android 的安装、信任步骤及厂商官方资料。

### 实际执行与结果

| 检查 | 实际结果 |
|---|---|
| 生产库只读审计 | `PRAGMA integrity_check=ok`、外键错误 0；库存流水余额与前后链、采购入库关联及被引用媒体摘要检查通过。核对时有 2 个账号、1 个批次、1 条流水、0 个采购项和 0 个媒体文件；未打印家庭食材内容 |
| 完整回归 | `.venv/Scripts/python.exe manage.py test tests --settings=config.settings.test` 退出码 0，64 项通过；`makemigrations --check --dry-run` 无差异；`pip check` 退出码 0 |
| 部署设置 | `scripts/manage_prod.ps1 check --deploy` 退出码 0，仅既有 `security.W004` HSTS 警告；项目通过局域网 IP 使用 HTTPS，已记录该警告原因 |
| 依赖核对 | 官方 Django 发布页显示 5.2.17 为检查当日 5.2 LTS 最新补丁；在独立 `work/audit-venv` 使用 `pip-audit --no-deps --disable-pip -r requirements.lock` 核对 12 个固定 Python 依赖，退出码 0，无已知漏洞。未扫描 Windows、Caddy、SQLite 和 Ollama |
| 登录任务及进程恢复 | 当前用户两个任务为 Running。分别中断 Waitress 与 Ollama 子进程后，守护脚本均在数秒内恢复 loopback 监听。首次只依赖任务计划程序的 RestartOnFailure 时，子进程退出并未触发任务重启，已改用脚本内守护并重测；整机重启未测 |
| 私有备份 | 首次停 Waitress 后备份 `household-20260925-185850-9799469e`；正式测试 `stop_waitress_for_backup.ps1` 退出码 0，随后 `backup_household` 退出码 0，生成 `data/backups/household-20260925-192704-bb25d42c/`，引用媒体 0 个。恢复登录任务后，可信 HTTPS 健康页为 200 |
| 恢复演练 | 从最新私有备份复制到独立 `work/stage07-restored-20260925-192738-f0f3c2d7/`；完整性、外键、业务表计数、附件摘要与 33 条迁移记录通过；在副本中清除 3 个旧会话，以现有活跃成员身份读取首页、冰箱、做什么、采购四页，均 200，退出后副本会话为 0。生产库未恢复或覆盖；当前生产媒体 0 个，所以未演练真实媒体恢复 |
| 家庭网络切换 | 用户确认新 `192.168.110.146/24` 为可信家庭 Wi-Fi。Caddy 配置验证后经管理员提升应用，服务 `Running`、`Automatic`、仍为 `LocalService`；只监听新地址 8443。入站规则只允许 Caddy、WLAN、该地址和 `192.168.110.0/24` 来源；Waitress/Ollama 仍只监听 loopback |
| 新地址 HTTPS | 用项目公开根 CA 严格验证，`/health/` 200、`/login/` 200、匿名 `/shopping/` 302、匿名 `/api/shopping/` 401、匿名 `/api/recipes/` 401、指纹静态文件 200 且长期缓存、普通 70 KB 请求 413。换网前旧地址探测超时；这不代表手机可连接 |
| 源码交接包 | `work/stage07_snapshot.py` 退出码 0；`outputs/stage07-source.zip` 收录 116 个明确列出的源码与文档文件，ZIP CRC 检查无坏项，排除 `data/`、`.venv/`、`work/`、数据库、附件、运行配置、密钥及日志 |

运行过程中的两个修正：注册任务时最初误用不存在的 `InteractiveToken` 枚举，改为 PowerShell `Interactive` 后注册成功；第一次管理员配置脚本把 Caddy 的正常 stderr 输出当作错误，在变更前退出，修正原生命令处理后才执行成功。最初恢复副本页面脚本未加入项目路径，修正后 4 页检查通过。以上失败均未被计为通过。

最终再次运行完整 64 项测试、部署检查、迁移差异检查、依赖完整性检查、生产库只读审计、新地址可信 HTTPS 探测及 5 个 PowerShell 脚本语法解析，全部退出码 0；部署检查仍只有前述 HSTS 警告。两个当前用户登录任务状态为 Running。

### 未完成与人工步骤

- **当前阻断：**用户确认手机能打开 `https://192.168.110.146:8443/shopping/`，但提示证书不受信任。待按手机系统安装并启用公开根 CA，再核对无警告访问；不要忽略警告输入密码。本机 HTTPS 成功不能替代真实手机无警告访问。
- **采购手机验收：**先确认新入口能无警告登录，再添加一项采购，核对“买到了”不增库存，按实际数量确认入库一次，并在冰箱查看批次与流水；有第二台设备时核对同一结果。用户尚未报告通过。
- **未执行：**真实手机拍照识别准确率和 200 MiB 视频上传、主机重启后的自动恢复、未登录时服务可用性、异设备受保护备份、真实故障时生产库切换、磁盘加密状态确认。非管理员读取 BitLocker 状态返回访问拒绝；不能据此推断启用与否。阶段 07 生产库没有采购项，也没有可供验证的真实附件。
- 源码 ZIP 与私有备份用途不同；`data/`、运行配置、密码、Cookie、媒体、日志和 CA 私钥均不交付到源码包。网络地址以后再变化，需要重新核对 Caddy、Django 和防火墙。具体运行步骤见 `HANDOFF.md`。

## 固定局域网网址（2026-09-26，阶段 07 补充）

**状态：**用户确认当前 “White Whale” Wi-Fi 可开放应用，新网络需先确认；电脑端固定入口已启用，Android 首次打开固定网址反馈“无法打开”，手机验收未通过。此补充只处理运维入口与交接，不扩产品功能。

### 代码与运行变更

- `config/Caddyfile` 改为 `https://shijinyong.local:8443/`；`scripts/initialize_runtime.ps1` 的首次 Host/Origin 默认同步。私有 `data/runtime.env` 已备份后原位更新，Waitress 登录任务已重启。未改数据库模型、迁移或业务数据。
- `requirements.lock` 加入 `zeroconf==0.151.3` 和 `ifaddr==0.2.0`；`scripts/publish_lan_name.py`、`scripts/start_lan_name.ps1`、`scripts/register_lan_name_task.ps1` 在当前用户会话发布 mDNS 名称。`scripts/network_guard.ps1` 的受保护副本由系统任务运行，按已确认的 SSID 与 AP BSSID 管理 Caddy、防火墙和活跃地址。当前受保护名单仅有已确认的 “White Whale” AP BSSID；未来新网络需先由用户确认，管理员再加入并重启任务。
- `docs/plans/2026-09-26-stable-lan-name-design.md`、`README.md`、`docs/{SOURCES,ENVIRONMENT,HANDOFF,PROGRESS}.md` 更新设计、来源、运行与限制。无 Git 仓库，源文件未自动提交；源码包仅包含明确列出的代码与文档。

### 实际检查

| 检查 | 结果 |
|---|---|
| 变更前备份 | 停止 Waitress 后，`backup_household` 退出码 0，在私有 `data/backups/household-20260926-170742-bf97eea5/` 生成数据库与 0 个引用附件的校验备份；随后恢复 Waitress |
| 安装与回退 | 首两次管理员部署未通过启动验收并回退；诊断发现 Windows 把 Caddy 双栈监听显示为 `::`，旧检查误认为没有 IPv4 监听。改为校验 Caddy 服务进程与当前 IPv4 真实连接后，第三次部署退出码 0；先前失败的受保护守护目录作为私有回退材料保留，不进入交付 |
| 当前网络边界 | 守护活跃地址为 `192.168.1.220`，状态持续更新；Caddy `LocalService` 运行，TCP 8443 防火墙规则为 Caddy/WLAN/当前地址/LocalSubnet，mDNS UDP 5353 规则限定名称发布程序/WLAN/LocalSubnet；Waitress `127.0.0.1:8000` 监听 |
| 名称与 HTTPS | 电脑 `Resolve-DnsName shijinyong.local` 返回 `192.168.1.220`；严格使用公开根 CA 校验 TLS 1.3，证书 SAN 含固定名，`/health/` 200、`/login/` 200、匿名 `/api/shopping/` 401。匿名 `/shopping/` 跳转到登录页；未绕过证书检查 |
| 网络条件 | 守护脚本对已确认名单的只读模拟返回当前 IP，合成错误 BSSID 返回 `trusted=none`。真实换网、DHCP 地址变化、守护异常退出、整机重启均未执行 |
| 回归与依赖 | 完整 Django 64 项测试退出码 0；`pip check` 退出码 0；新增依赖的隔离 `pip-audit` 退出码 0，无已知漏洞。`check --deploy` 退出码 0，仅 `security.W004` HSTS 警告；手机证书信任稳定前暂未启用 HSTS |

### 未完成与人工步骤

- Android 手机在 “White Whale” 首次打开 `https://shijinyong.local:8443/` 反馈“无法打开”；已请求具体浏览器错误与 `https://192.168.1.220:8443/` 的连通结果，等待区分名称解析与网络连通问题。**手机固定地址尚未上线验收。**
- 手机此前访问旧 IP 地址出现证书不受信任；需要在 Android 安装并信任 `outputs/shijinqiyong-root.cer` 对应的家庭根 CA，核对 `HANDOFF.md` 指纹，无警告后才能登录。用户仍需完成“买到了不增库存 → 确认入库一次 → 流水”的真实采购验收。
- 真实未知网络与重启场景未测试。系统守护任务若异常退出，已启用的防火墙规则不会自动过期，不能据合成模拟宣称未知网络隔离已实测。已确认网络的 mesh 新 AP BSSID 也需要再次确认。

**下一步：**先根据 Android 的具体错误和 IP 直连结果修复固定地址访问，再做无警告 HTTPS 与采购手机验收；阶段 07 的异设备备份和主机重启验收仍待执行。

## 固定名称暂停，恢复 IP 入口（2026-09-26）

用户要求“像以前那样先开开，这个东西过一会再搞”。固定名称实验已暂停，**当前入口为 `https://192.168.1.220:8443/`**。先前文档中的固定名称运行状态是历史记录，不能作为当前地址使用。

- Android 截图的错误详情明确为 `https://shijinqiyong.local:8443/` 的 `ERR_NAME_NOT_RESOLVED`；当时部署的是漏掉 `qi` 的 `shijinyong.local`。截图地址栏后来显示 IP，但弹出的详情仍是前一次域名错误，因此不能据此认定 IP 不通。曾试图切换到完整拼音名，网络守护重新启动未通过验收，脚本回退并关闭入口；遵照用户的新指示，停止该实验。
- `config/Caddyfile` 与 `scripts/initialize_runtime.ps1` 已改回当前 IP；私有运行配置备份后改回 IP Host/CSRF Origin，Waitress 重启。管理员脚本 `work/restore_current_ip_entry.ps1` 退出码 0：受保护网络守护任务禁用，Caddy 设为 Automatic 并监听 `192.168.1.220:8443`，防火墙仅放行 Caddy/WLAN/当前 IP/`192.168.1.0/24`，mDNS 规则禁用。当前用户 `ShiJinQiYong-LanName` 禁用，两个名称发布 Python 子进程已停止。未改数据库或业务迁移。
- 电脑使用原公开根 CA 严格校验证书，请求 `/health/` 200、`/login/` 200、匿名 `/shopping/` 302、匿名 `/api/shopping/` 401，探测退出码 0。`check --deploy` 退出码 0，仅既有 HSTS 警告。Caddy 实际监听当前 IPv4，Waitress 仅 `127.0.0.1:8000`；防火墙范围已核对。
- **未执行/待人工：**手机新 IP 入口、手机根 CA 无警告信任、采购真实流程、整机重启后的恢复。已请求手机打开 `https://192.168.1.220:8443/health/` 回报结果。后续新网络须先确认，再调整 IP、Caddy、Django Host/Origin 和防火墙；固定名称方案只有用户再次要求时才继续。

用户随后反馈 Android 手机打开当前 IP 的 `/health/` 时出现证书警告，点击继续后显示 `ok`。这实测证明手机到当前 Caddy 入口可达，但**没有通过无警告可信 HTTPS 验收**；不能把这次继续访问算成可安全登录。需在 Android 安装并信任原家庭根 CA 后重新检查，证书指纹与步骤见 `HANDOFF.md`。上条“手机新 IP 入口未执行”已由此次诊断访问替代，采购真实流程仍未执行。

当前状态复核：`pip check` 退出码 0，`makemigrations --check --dry-run` 无差异；`work/current_ip_snapshot.py` 退出码 0，`outputs/current-ip-source.zip` 收录 121 个明确列出的源码和文档文件，ZIP CRC 检查通过，不含 `data/`、`.venv/`、`work/`、运行配置与私有文件。无 Git 仓库，旧的 `outputs/stage07-source.zip` 保留为历史快照。

## 阶段 07A 早期实施记录（2026-09-26）

用户明确授权在原 Django 技术栈内增加可选服务端菜谱生成与单个本地工作进程。实施前已读根约定、架构、进度、API、既有菜谱/采购/库存及部署代码。当前目录没有 Git；源码基线保存在 `outputs/stage07a-before-source.zip`，121 个文件 CRC 核对通过。按既有安全流程停 Waitress 后执行私有备份，成功生成 `data/backups/household-20260926-201734-d24936b8/`，随后恢复 Waitress。以上回退材料未包含在交付源码中。

已增量完成：`meals` 兼容迁移 0002、0003；8 道结构化本地菜谱（保留旧编号）、13 项后扩至 14 项可追溯 USDA SR Legacy 营养映射，未知字段保留空值；数量/状态/器材/限制核对与统一菜单分配；个人和家庭口味表单；明确确认后复用原购物和库存事务服务；默认关闭的 AI 提供者适配、任务表和单进程工作命令；手机工作台、候选、菜单、教程和任务页。更新 `AGENTS.md`、`docs/ARCHITECTURE.md` 并保存实施设计。真实模型密钥尚未提供，生产外部生成未启用。

实际测试：原 64 项回归在阶段 07A 初始代码后退出码 0；新增 11 项规则与菜单测试退出码 0。新测试包括缺盐严格拒绝、500 克需求与 300 克库存形成 200 克缺口、备选合菜单不重复占用、禁用批次排除、营养未知、权限、恶意结构拒绝、采购幂等及实际使用流水。安全温度规则和菜单页面在此后又补充了代码，待最终完整回归重测。尚未把测试替身冒充真实模型联调。

待完成：新增任务与权限边界测试、三组端到端演示、性能与备份恢复复测、生产迁移及静态文件收集、文档与交接。阶段 07 的 Android 无警告 HTTPS、采购手机验证和主机重启验收仍未完成；本阶段不会宣称其通过。

## 阶段 07A 交付核对（2026-09-26）

**代码状态：**在原 Django 单体上增量完成结构化菜谱、条件确认、数量和批次分配、严格/允许补购、口味配置、可追溯营养估算、菜单采购及实际使用、可选生成任务。8 道详细本地参考菜谱保留原 6 个 ID，来源均标明未实测；14 项 USDA SR Legacy 本地营养参考缺失字段维持未知。`AGENTS.md` 和 `ARCHITECTURE.md` 已记录仅限本阶段的 AI 与工作进程例外。没有重建项目、重置账号或覆盖生产食材。

**生产数据：**迁移前通过既有备份流程保存源码快照与私有备份；生产迁移 `meals.0002`–`0005`、静态资源收集均退出码 0。迁移后只读完整性、外键和计数检查通过：原账号 2、批次 1、库存动作 2、流水 1、家庭菜谱与采购项 0（与迁移前备份计数一致）；新增营养参考 14。阶段 07A 最新私有备份 `data/backups/household-20260926-211032-0a7d6254/` 已在独立目录 `data/restore-drill-stage07a-b91780dd/` 恢复，核对完整性、外键、14 项参考、0 个媒体文件、清除旧会话及登录后 5 个页面 200；生产库未被替换。

**实际测试：**最终完整回归 91 项通过，含 27 项阶段 07A 测试；`makemigrations --check --dry-run` 无差异、`pip check` 无冲突、`check --deploy` 退出码 0 且仅既有 `security.W004` HSTS 提示。校验覆盖缺盐严格拒绝、500−300 克净差额、非重量单位不偷换、菜单不重占、禁用批次、旧版本再检查、营养未知与按实际油量重算、偏好探索和硬限制、私人数据隔离、教程一致性与恶意结构拦截、生成任务成功/失败/取消/超时的测试替身、原库存流水。隔离副本读页面 p95 为冰箱 7.4 ms、原菜谱页 8.0 ms、工作台候选 120.4 ms、采购 9.2 ms；20 次库存创建 p95 11.0 ms。测试里的模拟慢模型等待期间，普通库存写入小于 1.5 秒。详见 `PERFORMANCE.md` 与 `ACCEPTANCE.md`；这些不是手机或真实模型端到端性能。

**运行网络：**用户此前确认的当前家庭 WLAN 为 `192.168.110.146/24`，Caddy 的 IP HTTPS、防火墙与私有 Django Host/Origin 已同步；电脑持公开根 CA 严格校验 `/health/`、`/login/` 为 200，匿名 API 为 401，普通 70 KB 请求为 413。Waitress 只在 loopback；固定名称实验保持停用。用户现报告 Android 在当前 `/health/` **仍有证书警告**，所以手机可信 HTTPS 和阶段 08 发布验收均未通过。不得在越过警告后输入密码。

**未完成及人工步骤：**没有模型凭据，真实模型未联调、外部生成默认关闭、菜谱工作进程未作为长期服务托管；真实模型慢调用下的端到端性能与费用也未测试。手机需安装并核对公开根 CA，在无警告 HTTPS 下完成阶段 06 采购闭环与本阶段三组家庭实际操作；主机重启恢复、真实双设备、异设备受保护备份、真实厨艺/安全人工核验待执行。当前 91 项测试与三组自动化演示不能替代这些现场步骤。旧地址与旧阶段“当前”描述是历史记录，现行入口、回退和权限说明见 `HANDOFF.md`、`ENVIRONMENT.md`、`SECURITY.md`。

**交付包最终核对：**`work/stage07a_snapshot.py` 生成 `outputs/stage07a-source.zip`，收录 150 个源码、公开参考数据与文档文件，ZIP CRC 通过。首次打包脚本误将 `meals/data/` 的公开菜谱和营养数据随私有 `data/` 一起排除，已修正并重建；最终包明确包含三份公开数据 JSON，且不含顶层私有 `data/`、`work/`、`.venv/`、数据库、运行环境文件、媒体、日志或 CA 私钥。最终只读生产库与迁移前备份计数一致：账号 2、批次 1、库存动作 2、流水 1、采购 0、家庭菜谱 0；营养参考新增 14，迁移 0002–0005 已登记。`work/stage07a_final_audit.py` 最终退出码 0。

**工作进程关闭态检查：**在生产设置执行 `run_recipe_worker --once`，退出码 0、输出 `worker_not_started=model_not_configured`；没有创建任务或伪造生成结果。

**采购数量可调整补充：**菜单理论净缺口与计划购买量分开显示，成员可在确认加入前修改后者；所选菜单贡献仍按菜单版本幂等记录，不重复创建。新增自动化覆盖调整与重复提交，最终完整回归 91 项（新增 27 项）通过。

**最终运行应用：**本次采购数量调整后重启 `ShiJinQiYong-Waitress` 登录任务，状态 `Running`，重新监听 `127.0.0.1:8000`；Caddy 仍监听 `192.168.110.146:8443`。随后用公开家庭根 CA 严格校验 HTTPS，`/health/`、`/login/` 为 200，匿名采购/菜谱 API 为 401，静态 CSS/JS 为 200，普通超限请求为 413。此为电脑端部署探测，**Android 仍有证书警告**。

## GitHub 源码交付与 macOS 运行说明（2026-09-26）

用户提供 `yangxufe/SHIJINQIYONG` 作为源码仓库，并明确要求上传现行版本，让获准访问者克隆后在各自本机运行。当前项目原目录没有 Git；只读克隆远端后看到 `main` 仅有初始 README，因此准备在克隆目录提交明确允许的源码文件，保留原电脑私有 `data/` 不上传。公开未授权仓库 API 查询返回 404；仓库具体访问权限由 GitHub 管理，最终上传和另一名协作者下载仍须以实际远端结果核对。

新增 `config/Caddyfile.macos`、`scripts/macos_setup.py`、`scripts/macos_runtime.py`、`scripts/setup_macos.sh`、`docs/MACOS.md` 和测试；更新 README、架构、来源、安全说明与示例配置。Mac 初始化会生成本机独立密钥、空 SQLite、成员账号及 Caddy CA；代理绑定人工确认的私有 IPv4，按明确 CIDR 限制来源，Waitress 仍只监听 loopback。Caddy 进程不会取得 Django 密钥。各 Mac 下载源码并不共享原电脑家庭数据；真正迁移需单独受保护备份，不能经 GitHub 分发。

实际检查：完整 Django 回归 94 项通过，新增 3 项 Mac 配置单元检查；`makemigrations --check --dry-run` 无差异，`pip check` 无冲突，`check --deploy` 退出码 0、仅既有 IP HSTS `security.W004`。在 Windows 开发机用 Caddy 对带模拟 Mac 环境变量的配置执行 `adapt` 与 `adapt --validate`，两者退出码 0；没有在真实 Mac 运行 Bash 安装、系统证书信任或手机访问。Windows 工具包不含 Bash，`bash -n` 未执行，不能把 Caddy 配置解析当作 Mac 端到端上线。

待上传后补记远端提交 ID、实际下载核对、文件排除审计与任何授权阻断。Mac 运行者仍须自行确认可信家庭网络、安装必要依赖、创建本地成员账号、信任本机新 CA，并按 `docs/MACOS.md` 现场测试。

**GitHub 实际上传与下载：**以明确的 156 文件白名单提交到 `yangxufe/SHIJINQIYONG` 的 `main`，首个程序提交 `d78346dc50a776bebbac16c35cec74591d51b158` 已推送成功；远端原有初始 README 保留在 Git 历史。提交前 ZIP CRC、路径/扩展名排除、常见私钥/令牌格式扫描与暂存名单一致性均通过，未上传生产 `data/`、`.venv/`、`work/`、`outputs/`、媒体、日志、运行配置、Cookie 或 CA 私钥。最初 `.gitignore` 的未锚定 `data/` 会误排除公开的 `meals/data/`，已改为仅忽略根目录 `/data/`，三份公开 JSON 均在提交中。

推送后以当前有权限的 Git 凭据从 GitHub **重新克隆**，取得同一提交、156 个受控文件；未用另一个协作者账号实测权限。下载副本第一次从原项目工作目录启动测试，因 Python 导入到原项目的 `tests` 失败；改在副本目录运行，发现尚未初始化的私有 `data/` 缺失。创建测试所需的空 `data/` 后，下载副本完整 94 项回归通过，原工作目录与数据库未作为测试输入。真正 Mac 首次安装脚本会创建该私有目录；Mac 实机安装、HTTPS 根证书信任和手机访问仍未执行。所有获得仓库读取权限并接受邀请的成员可按 `docs/MACOS.md` 下载程序；GitHub 权限授予与成员的实际下载仍须由仓库所有者及该成员验证。

## 页面局部调整（2026-09-26）

- “今天”仅显示标题与“计划日期是安排提醒，不是安全期限。”，退出登录移至右上；管理员的家庭设置入口随之移到右上。今天库存 API 保留，未改库存服务。
- “冰箱”的新建和编辑表单隐藏“包装日期原文”。数据库字段与 API 保留；编辑时不提交该字段，已有原文不会被清空。日期、数量、流水与拍照入口未改。
- “做什么”的“生成搜索入口”改为独立 `/recipes/search-results/` 页面；空白输入在浏览器端阻止跳转，服务端空白/超长请求返回原页提示。旧 `/recipes/?find=` 链接转到新页面。外站搜索仍由用户点击才打开，不写库存或采购。
- 变更文件：`config/urls.py`、`meals/views.py`、`templates/core/index.html`、`templates/inventory/{list,edit}.html`、`templates/meals/{list,search_results}.html`、`static/{css/app.css,js/recipe-search.js}`、`tests/{test_family_recipes,test_stage04,test_page_adjustments}.py`、`docs/{API,PROGRESS}.md`。无模型或数据库迁移。

**实际验证：**隔离测试设置下页面专项 8 项通过，完整 97 项回归通过；`makemigrations --check --dry-run` 无差异，`git diff --check` 退出码 0。隔离合成账号的真实浏览器点击验证了空输入提示、有效输入跳转、结果页返回；320/360/390/1280 CSS 像素检查了相关页 `scrollWidth <= innerWidth`。这不是 Android 实机测试。生产 `collectstatic` 退出码 0（2 文件复制、6 文件后处理），Waitress 登录任务重启后恢复 `127.0.0.1:8000`，Caddy 仍监听原已确认的 `192.168.110.146:8443`。使用公开根证书经 Python 标准 TLS 校验 `/health/` 200、新 JS 200，匿名新页面跳到登录页；Windows curl 的 Schannel 对同一 DER 根证书报“certificate chain is incomplete”，不将其记作成功。`check --deploy` 退出码 0，仅既有 HSTS 提示。

**待核对：**当前模板没有自定义的左右切换箭头，只有分页“上一页/下一页”文字和浏览器原生日期/下拉控件；已请用户指出箭头所在方框或提供截图，未猜测性修改其他控件。Android 可信 HTTPS 警告与手机端本轮页面验收仍待用户实测；真实家庭数据未用于浏览器测试。GitHub 上传状态与本轮最终提交另行补记。
