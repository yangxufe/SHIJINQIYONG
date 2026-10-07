# 官方资料与查证范围

## Windows 自动安装查证（2026-10-07）

[Python 官方 NuGet 运行环境](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages)、[CPython 3.13.16 包与维护者](https://www.nuget.org/packages/python/3.13.16)、[Python 3.13.16 发行说明](https://www.python.org/downloads/release/python-31316/)、[Caddy v2.11.7 发行及校验文件](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)、[Caddy 内部 HTTPS](https://caddyserver.com/docs/automatic-https)。运行包版本及散列见 config/windows-downloads.json；Python 包实际 HTTPS 下载后计算 SHA-256，并校验内部 python.exe 的 Python Software Foundation Authenticode；Caddy使用发行方 SHA-512。

## 阶段 07A 补充查证（2026-09-26）

macOS 本机运行与局域网 HTTPS 的资料（2026-09-26）：[Caddy Mac 安装](https://caddyserver.com/docs/install)、[Caddy 本地 CA 与其他设备信任](https://caddyserver.com/docs/automatic-https)、[Caddyfile 环境变量](https://caddyserver.com/docs/caddyfile/concepts)、[Caddy remote_ip 匹配](https://caddyserver.com/docs/caddyfile/matchers)、[Waitress 监听地址](https://docs.pylonsproject.org/projects/waitress/en/latest/arguments.html)。`docs/MACOS.md` 的自动化脚本在 Windows 开发环境做过单元与 Caddy 配置解析检查，未在真实 Mac 执行。

- USDA FoodData Central [可下载数据集](https://fdc.nal.usda.gov/download-datasets/)：使用其中 SR Legacy 2018-04 CSV 的 `food.csv`、`nutrient.csv`、`food_nutrient.csv` 提取 14 项本地参考；每项保留 FDC ID、原英文食物描述、版本、来源链接和查询日期。普通推荐不在运行时查询 USDA。缺失的添加糖等字段维持未知，不推断为零。
- USDA FSIS [安全中心温度表](https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/safe-temperature-chart)：`meals/safety_rules.py` 的有限规则和来源。自动检查只能拦截已知问题；未实测菜谱不写成已经安全验证。
- [Ollama generate API](https://docs.ollama.com/api/generate)：本机固定 loopback `/api/generate`，支持 `format` JSON Schema、`stream: false`；模型名称由管理员按实际安装填写。
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat)：可选固定官方 HTTPS 地址及 JSON Schema `response_format`；实际可用模型由管理员验证，未写死名称、报价或联调结果。外部生成默认关闭。

核验日期：2026-09-25。以下用于解释框架能力与限制；架构选型、工期、性能预算及发布规则是本方案的设计决策，不是资料证明的已达成结果。实施当天重新核查安全补丁，不从本文推断“永远最新”。

[S1] Django 下载与支持版本表：5.2 LTS 延长支持期至 2028 年 4 月；安装当前安全补丁。  
`https://www.djangoproject.com/download/`

[S2] Django 安全：模板转义、SQL/CSRF 防护、Host、HTTPS及其限制。  
`https://docs.djangoproject.com/en/5.2/topics/security/`

[S3] Django 身份系统：内置用户/权限/会话集成，不自带完整登录节流或对象权限。  
`https://docs.djangoproject.com/en/5.2/topics/auth/`

[S4] Django 密码管理：Argon2id、配置及密码验证。  
`https://docs.djangoproject.com/en/5.2/topics/auth/passwords/`

[S5] Django CSRF 使用：普通表单、fetch头、HttpOnly时从DOM取token与测试检查。  
`https://docs.djangoproject.com/en/5.2/howto/csrf/`

[S6] Google Web Vitals：LCP≤2.5s、INP≤200ms、CLS≤0.1及75百分位判定。  
`https://web.dev/articles/vitals`

[S7] Django 数据库访问优化：测量、查询与索引、select_related/prefetch_related。  
`https://docs.djangoproject.com/en/5.2/topics/db/optimization/`

[S8] Waitress 参数与用法：线程、监听、代理信任、请求体限制。  
`https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html`  
`https://docs.pylonsproject.org/projects/waitress/en/stable/usage.html`

[S9] SQLite WAL：并发/同主机限制、WAL-reset 修复及版本范围。  
`https://www.sqlite.org/wal.html`

[S10] SQLite 事务与隔离：单写入者、IMMEDIATE、冲突。  
`https://www.sqlite.org/lang_transaction.html`  
`https://sqlite.org/isolation.html`

[S11] Django SQLite 后端：IMMEDIATE、短事务、ATOMIC_REQUESTS、select_for_update无效、decimal限制。  
`https://docs.djangoproject.com/en/5.2/ref/databases/`

[S12] Caddy Automatic HTTPS：本地CA、客户端信任、公开根证书与私钥边界。  
`https://caddyserver.com/docs/automatic-https`

[S13] django-axes 维护者文档：安装、认证集成与配置；具体设置以所装版本文档为准。  
`https://django-axes.readthedocs.io/en/latest/2_installation.html`  
`https://django-axes.readthedocs.io/en/latest/3_usage.html`  
`https://django-axes.readthedocs.io/en/latest/4_configuration.html`

[S14] OWASP 会话与CSRF：Cookie保护、SameSite不能替代CSRF。  
`https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html`  
`https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html`

[S15] 反向代理与Django部署检查：只信任受控代理、生产安全配置。  
`https://caddyserver.com/docs/caddyfile/directives/reverse_proxy`  
`https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header`  
`https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/`

[S16] MDN CSP：限制脚本等来源、避免不安全内联与eval；是纵深防御的一层。  
`https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP`

[S17] Python sqlite3 backup：运行中的数据库备份接口。  
`https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup`

[S18] MDN HSTS：HSTS按域名识别主机，IP地址不能成为HSTS host。  
`https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security`

原产品规则承接同对话文件 xianchi_plan.md，特别是批次与日期、菜谱确认、采购入库、备份和真实设备验收。新方案对认证、HTTPS、技术栈与排期作了明确替换，不能混用旧部署命令。

拍照录入补充资料（2026-09-25 核对）：

- [Ollama Vision](https://docs.ollama.com/capabilities/vision)：本机 REST API 用 base64 图片数组发送视觉请求。
- [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)：视觉模型可指定 JSON schema，但应用仍需校验实际输出。
- [Pillow 安全说明](https://pillow.readthedocs.io/en/stable/handbook/security.html)：限制解压像素并在重新编码时去除图像元数据。
- [MDN capture 属性](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture)：手机文件输入可请求后置相机，浏览器兼容性仍需实际设备核对。

家庭菜谱与私有媒体补充资料（2026-09-25 核对）：

- [Django 文件上传](https://docs.djangoproject.com/en/5.2/topics/http/file-uploads/)：`request.FILES`、分块读取、大文件临时存储及上传安全边界；本项目的视频按块写入私有目录。
- [Django StreamingHttpResponse](https://docs.djangoproject.com/en/5.2/ref/request-response/#django.http.StreamingHttpResponse)：认证后流式返回视频；应用自行实现单段 Range 校验。
- [Caddy request_body](https://caddyserver.com/docs/caddyfile/directives/request_body)：按路径设置请求体上限。
- [MDN Range 请求头](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Range)：浏览器视频分段读取的请求与响应语义。
- [B 站搜索页面示例](https://search.bilibili.com/all?keyword=%E7%95%AA%E8%8C%84%E7%82%92%E8%9B%8B)：仅作为成员主动打开的外部视频搜索入口，不是应用后台 API，也不承诺该网站始终可用。

阶段 07 依赖复核资料（2026-09-25 核对）：

- [Django 官方下载页](https://www.djangoproject.com/download/)：核对 5.2 LTS 分支当前发布补丁；运行环境为 5.2.17。
- [Django 安全公告](https://www.djangoproject.com/weblog/2026/aug/04/security-releases/)：核对该补丁所属安全发布说明。
- [PyPA pip-audit](https://github.com/pypa/pip-audit/blob/main/README.md)：对 `requirements.lock` 中的固定 Python 依赖执行公开漏洞库核对；此扫描不覆盖 Windows、Caddy、SQLite 或 Ollama。

固定局域网名称补充资料（2026-09-26 核对）：

- [RFC 6762 Multicast DNS](https://www.rfc-editor.org/rfc/rfc6762)：`.local` 名称在本地链路通过组播解析，不保证跨子网或访客网络可达。
- [Android DNS Resolver](https://source.android.com/docs/core/ota/modular-system/dns-resolver)：Android 系统解析器对 `.local` 的 mDNS 支持；具体手机浏览器仍需实测。
- [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)：本地 CA 颁发主机名证书，客户端必须自行信任该 CA。
- [Caddy bind](https://caddyserver.com/docs/caddyfile/directives/bind)：监听接口配置；Windows 实际监听地址仍以本机检查为准。
- [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf)：固定名称的本机 mDNS 发布实现。

第一次优化与 YOLO 资料（2026-10-03 核对）：

- [YOLO-World 官方文档](https://docs.ultralytics.com/models/yolo-world/)：v2 支持固定离线词表与 ONNX 导出。本轮不是专用食材训练。
- [官方预训练权重](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt)：实际构建输入，原权重与导出散列记录在 model_assets/yolo-food.json。
- [Ultralytics 导出说明](https://docs.ultralytics.com/modes/export/)：本轮固定 640、opset 17、无内置 NMS，后处理由应用服务端执行。
- [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary.html)、[线程管理](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)：CPU 会话、两线程、关闭线程空转。
- [Ultralytics 模型许可](https://www.ultralytics.com/license)：AGPL-3.0 或另行企业许可；附上游 AGPL 全文，不替用户决定其他自写代码的许可。
- [公开 COCO128 样本](https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip)：实际 smoke 测试含成功、未检出及需核对候选，不能当作完整家庭食材验证。
- [Django 表单认证](https://docs.djangoproject.com/en/5.2/topics/auth/default/#django.contrib.auth.forms.UserCreationForm)、[Django signing](https://docs.djangoproject.com/en/5.2/topics/signing/)：邀请注册使用现有账号与密码机制、签名和有效期，未设计新登录协议。
