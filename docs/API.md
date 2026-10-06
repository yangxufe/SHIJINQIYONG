# 食尽其用接口合同（阶段 05 与家庭菜谱扩展）

同源 HTTPS，所有路径带尾斜杠。请求使用 Django 会话；浏览器写请求必须带 CSRF token。未登录首页跳转 `/welcome/`，其他业务页跳转 `/login/`；`/api/` 未登录返回结构化 401。注册页公开但必须有效管理员邀请，没有无需邀请的公开注册或 Django admin。

## 已运行

| 方法 | 路径 | 权限 | 响应 |
|---|---|---|---|
| GET | `/login/` | 公开 | 登录表单，200 |
| POST | `/login/` | 公开 + CSRF | 成功 302；失败显示表单；节流 429 |
| POST | `/logout/` | 已登录 + CSRF | 注销会话，302；GET 405 |
| GET | `/` | 成员或管理员 | 内部首页，200；四个入口：添加菜品、食材列表、查看菜谱、采购计划 |
| GET | `/recipes/` | 成员或管理员 | 内置与家庭菜谱按真实可用批次排序；支持 `category`、`q` 筛选，并提供教程关键词输入；查看不扣库存。旧的 `?find=` 链接会跳转独立结果页 |
| GET | `/recipes/search-results/?find=关键词` | 成员或管理员 | 在独立页面展示固定网站的视频、文字和图片搜索入口；空白或超过 80 字则返回原页提示；不扣库存 |
| GET、POST | `/recipes/new/` | 成员或管理员；POST 需 CSRF | 录入家庭私有菜谱、分类、标签与原教程链接；成功 302，非法表单 422 |
| GET | `/recipes/{id}/` | 成员或管理员 | 菜谱做法、缺少食材与可用批次，200；不存在 404 |
| GET、POST | `/recipes/{id}/edit/` | 成员或管理员；POST 需 CSRF | 仅 `family-{uuid}` 可编辑；要求当前版本，成功 302，冲突 409 |
| POST | `/recipes/{id}/cook/` | 成员或管理员 + CSRF | 确认每种食材实际使用的批次和数量，复用库存事务服务；成功 302，失败 409/422/503 |
| POST | `/recipes/{id}/upload/` | 成员或管理员 + CSRF | 仅家庭菜谱；上传 1 个图片或视频，成功 302；每菜最多 6 图、1 视频 |
| GET、HEAD | `/recipes/{id}/media/{media_uuid}/` | 成员或管理员 | 私有附件读取；视频支持单段 `Range`，成功 200/206，非法范围 416 |
| POST | `/recipes/{id}/media/{media_uuid}/delete/` | 成员或管理员 + CSRF | 删除家庭菜谱附件；成功 302 |
| GET、POST | `/shopping/` | 成员或管理员；POST 需 CSRF | 采购清单与新增采购项；同名已有库存或待办时须明确确认 |
| POST | `/shopping/{id}/bought/` | 成员或管理员 + CSRF | 标记买到，不增加库存 |
| POST | `/shopping/{id}/receive/` | 成员或管理员 + CSRF | 核对实际数量后唯一入库，记录正向流水 |
| POST | `/shopping/{id}/cancel/` | 成员或管理员 + CSRF | 取消未完成采购项 |
| GET | `/settings/` | 成员或管理员 | 家庭设置与个人配置入口，200；发邀请/家庭默认配置修改仍须管理员 |
| GET | `/api/settings/` | 管理员 | 尚未配置时 501；成员结构化 403 |
| GET、POST | `/inventory/` | 成员或管理员 | 添加菜品；POST 复用库存服务，成功跳食材列表；旧 GET 带 q/page 时保留参数跳新列表 |
| GET | `/inventory/list/` | 成员或管理员 | 食材列表，原搜索、分页、编辑、用量/丢弃/校正入口；参数及权限沿用原列表 |
| GET、POST | `/inventory/{id}/edit/` | 成员或管理员 | 编辑非数量字段；POST 复用库存服务 |
| POST | `/inventory/action/` | 成员或管理员 | 单批次实际用量/丢弃/校正；复用库存服务 |
| GET | `/health/` | 公开 | 仅 `{"status":"ok"}`，200；其他方法 405 |
| GET | `/static/...` | 公开 | Caddy 从独立静态目录提供本地指纹资源 |

## 已开放的库存 API

JSON 写请求必须使用 `Content-Type: application/json`，并从页面隐藏字段读取 CSRF token，放在 `X-CSRFToken`。未知字段、重复 JSON 键、非法数量或日期直接拒绝。所有写入要求由客户端生成并在重试时保持不变的 UUID `request_id`。同一操作者同一编号同规范化参数返回原响应，不增加流水；不同参数返回 409。网络超时应查询动作结果或用原编号、原参数重试，不生成新编号。

| 方法 | 路径 | 状态 |
|---|---|---|
| GET | `/api/inventory/?q=番茄&page=1&per_page=50` | 200；按批次/食材名称过滤、更新时间倒序，默认 50、最多 100 条/页；搜索词最多 80 字 |
| POST | `/api/inventory/` | 201；创建批次，同时记录正向入库流水 |
| POST | `/api/inventory/recognize/` | 200；本机视觉模型给出单个食材名称建议，不写库存；需登录与 CSRF |
| PATCH | `/api/inventory/{id}/` | 200；只编辑元数据，必须提交当前 `version` |
| POST | `/api/actions/` | 200；做饭、直接食用、真实丢弃、库存校正，可一次最多 20 批次 |
| GET | `/api/actions/{id}/` | 200；仅原操作者可查，返回 `original_status` 与 `result` |
| GET | `/api/actions/by-request/{uuid}/` | 200；仅原操作者按请求编号查询已提交动作；未找到为 404，不能推断写请求已取消 |
| GET | `/api/movements/?page=1&per_page=50` | 200；按时间倒序，默认 50、最多 100 条/页 |
| GET | `/api/today/` | 200；服务器计算“先安排”与“需要核对”，各返回前 3 批与总数 |
| GET | `/api/recipes/` | 200；返回本地菜谱的名称、所需/缺少食材、已找到种类数；不写库存 |

拍照识别仅接收 JSON `{"image":"<JPEG 的 base64>"}`，返回 `{"ingredient_name":"番茄","uncertain":false}`。浏览器会先缩图并转为 JPEG；服务端支持 JPEG、PNG、WebP 解码，但最多接收 2.5 MB 原始图像、2,000 万像素，输出不含照片。模型没认出时名称为空且 `uncertain=true`；失败返回结构化 422 或 503。建议名称必须由成员核对，数量、单位、位置、储存状态和包装日期不会从照片推断。该接口不会创建动作、批次或流水。

创建批次示例（日期字段可省略；不能把包装日期与计划日期混用）：

```json
{"request_id":"f658be17-83bd-447f-a6a8-e5375e1d44da","ingredient_name":"番茄","name":"周末买的番茄","quantity":"3","unit":"piece","location":"fridge","storage_status":"verified","package_date_status":"not_applicable"}
```

可用单位：`g`、`kg`、`ml`、`l`、`piece`、`pack`；位置：`fridge`、`freezer`、`pantry`、`other`。批次初始状态可为 `active` 或 `suspect`，储存状况可为 `verified` 或 `needs_check`，后者默认。`package_date_status` 为 `known` 时必须有 `package_date`（`YYYY-MM-DD`）；`unknown` 或 `not_applicable` 时包装日期必须为空。可单独记录 `package_date_text` 原文、`planned_use_date`、`purchase_date`、`opened_date`。`manual_priority` 是可选布尔值，默认 `false`；普通表单传 `"true"`/`"false"`。计划日期不是安全期限。

元数据编辑示例：

```json
{"request_id":"da258c38-3b9f-4d22-81cf-7703619f4bd2","version":0,"location":"fridge","storage_status":"verified"}
```

允许编辑名称、位置、计划/包装/采购/开封日期、包装日期原文与状态、食材状态、储存状况和 `manual_priority`。`quantity`、`unit`、食材标识不能从 PATCH 改写；疑似变质状态不能由普通编辑解除。所有成功编辑增加版本。归档批次不可再普通编辑。

实际用量示例：

```json
{"request_id":"590af544-dcc2-4781-a6b6-c4321e9672aa","kind":"cook","items":[{"lot_id":1,"version":0,"quantity":"1","unit":"piece"}],"note":"晚餐"}
```

`kind` 可为 `cook`（用于做饭）、`eat`（直接食用）、`discard`（真实丢弃）、`correct`（库存校正）。前三类 `quantity` 是本次变化量，必须大于零；`correct` 的 `quantity` 是校正后的**剩余量**，可以为零，且 `note` 必填。每项都要给出批次当前版本和与批次相同的单位；不同单位不会换算。重复批次拒绝，任一项失败全部回滚。零剩余量归档。只有状态为在库、储存已核对且包装日期未过的批次可记为做饭或直接食用；疑似变质批次可记录丢弃，但不能作为可用食材。应用不据此声称食品绝对安全。

创建、编辑和动作成功响应都包含 `action_id`、`request_id` 与结果；创建为 201，其余写入为 200。同键重试返回同一状态码和同一结果。流水包含批次、动作、变化量、单位、前后余额与时间；初始入库也有流水。

今日接口按家庭设置中的时区计算日期；尚无家庭设置记录时使用服务器显式配置时区。可安排批次必须在库、数量大于零、储存已核对且包装日期未过，按手动优先、计划日期（无日期排后）、入库时间与 ID 稳定排序。疑似变质、储存待核对和包装日期已过的批次只进入“需要核对”。计划日期逾期仅写“计划已过”，不推断食材已变质；无包装日期且标记“不适用”的批次仍可在储存已核对时安排。

## 本地菜谱与用量确认

基础菜谱来自本地 `meals/data/recipes.json`，保留原 6 道与显式别名表；阶段 07A 另有 `meals/data/structured_recipes.json` 的 8 道详细参考教程，新增菜谱可在旧列表查看。旧列表只表示食材名称存在，仍不表示数量足够；数量精确匹配请进入工作台。`GET /api/recipes/` 的 `recipes` 项包含 `id`、`name`、`ingredients`、`missing`、`matched_count`、`ingredient_count` 和 `has_all`。

详情页普通表单要求每种所需食材至少填写一个批次的实际用量。字段为 `request_id`、`quantity_{lot_id}`、`version_{lot_id}`；数量仍为最多三位小数的十进制字符串，单位取该批次实际单位。提交后服务端核对所选批次属于菜谱，再调用已有 `apply_action(kind="cook")`；版本冲突、库存不足、疑似变质、储存待核对或包装日期已过则整个动作回滚。成功后每批次产生流水，同一成员相同请求编号与参数重试返回原动作，即使批次已用尽也不会再扣一次。只看菜谱或打开详情不会扣库存。

家庭菜谱的 ID 为 `family-{uuid}`，与内置菜谱 ID 分开；做饭表单另带 `recipe_version`，阻止用已过时的家庭菜谱新扣库存。已提交的相同请求编号及原参数可在菜谱后续编辑后返回原动作。列表按当前可用食材种类的匹配比例、匹配数和稳定顺序排列。`category` 为荤菜/素菜/汤羹/其他时按新增的 `category_group` 分组过滤；其他值保留原分类精确过滤，原 `category` 返回值和数据库内容不变。`q` 在菜名、食材和标签中查找；最长分别为 20、80 字。`GET /api/recipes/` 同样支持这些筛选，分类列表固定为上述四组。内置菜谱按明确 ID 归类，家庭四类直接采用、清淡素菜归素菜、其他自定义类归其他。未列入显式别名表的家庭食材名仅精确匹配；浏览分组不代表禁食适用性。

`POST /recipes/new/` 普通表单字段：`title`、`ingredients_text`（每行一种主要食材）、`steps_text`（每行一步）、`category`、`tags_text`（逗号分隔）、`source_type`（`own`/`video`/`article`/`images`）、`source_url`、`source_note`、UUID `request_id`。自写菜谱必须填写步骤；文字教程至少填写步骤或 HTTPS 原链接；视频和图片教程可先建记录，再上传本机文件，也可保存外站 HTTPS 链接。创建同一成员同一请求编号、同内容返回同一菜谱，不会重复创建；不同内容 409。编辑表单另含当前 `version`，过期版本 409。家庭成员共享查看和编辑；无家庭角色及匿名账号被服务端拒绝。

网页的外部搜索入口由用户输入 `find` 关键词后在独立结果页生成；浏览器端阻止空白输入，服务端也会拒绝空白与超长输入。只有点击外部链接时浏览器才访问搜索网站。应用不抓取、复制或嵌入外站内容；原网页和视频需要网络连接且可能变化。保存的是用户填写的链接与笔记，本机上传的附件另存于私有数据目录，均不在公开静态目录。

附件上传为 `multipart/form-data`，字段 `file`、`kind`（`image`/`video`）、`caption`、UUID `request_id`，普通表单携带 CSRF。图片输入最多 8 MiB、2,000 万像素，仅接受可解码的 JPG/PNG/WebP，并重新编码为去元数据 JPEG；每菜最多 6 张。视频最多 200 MiB、每菜 1 个，接受 MP4、MOV、WebM 的对应容器头；不自动转码，浏览器播放兼容性需手机验证。重试原编号、原文件和说明不会重复保存；不同内容复用编号返回 409。Caddy 仅此上传路径允许 220 MB，请求超出上限可能在代理层返回 413；其它路由仍为 64 KiB，原拍照识别路径仍为 4 MB。私有附件读取需登录，动态响应 `no-store`，不通过 Caddy 的 `/static/` 提供。

## 采购与唯一入库

`GET /api/shopping/` 返回待办、最近完成记录和当前可用库存的名称/单位汇总；只读，不写库存。仅统计在库、储存已核对、包装日期未过的批次。已知别名归为同一名称，未收录名称精确比较；不同单位分开显示，不推断换算、是否足量或食用安全。

`POST /api/shopping/` 使用 `{"request_id":"UUID","name":"番茄","quantity":"2","unit":"piece","confirm_duplicate":false}` 新增待买项。若冰箱已有同名记录（可用或待核对），或清单已有待买/买到项，返回 409 `possible_duplicate`，不创建记录；待核对记录只用于提醒，不计入可用库存。成员核对后可用同一编号、将 `confirm_duplicate` 设为 `true` 再提交。同名检查也在写事务内复核。数量最多三位小数，始终作为十进制字符串传输。

`POST /api/shopping/{id}/bought/` 和 `/cancel/` 接收 `{"request_id":"UUID","version":0}`。买到只将状态变为 `bought`，不会产生库存批次或库存流水；取消仅适用于未完成项。两者持久记录动作并更新版本，陈旧版本或状态返回 409。

`POST /api/shopping/{id}/receive/` 仅允许已买到的项，示例：`{"request_id":"UUID","version":1,"quantity":"1.5","location":"fridge","storage_status":"needs_check","status":"active","package_date_status":"not_applicable"}`。实际数量可与计划不同，单位沿用采购项且不换算。可填 `package_date` 和 `purchase_date`；包装日期状态为 `known` 时必须给出日期，留空采购日期按家庭时区记今天。储存默认待核对，因此在用户核对前不会进入可用推荐。此请求在同一事务内建立批次、正向库存流水、购物项一对一入库关联和持久结果；同一请求编号重试返回原响应，即使不同编号也不能让同一购物项再次入库。

所有采购写请求需登录、CSRF、JSON `Content-Type`、UUID 请求编号；相同成员、编号与参数重试返回原状态和正文，编号用于不同参数返回 409。普通网页表单具有同等服务端验证。方法不符为 405。

## 阶段 07A 菜谱工作台与生成任务

2026-10-06 表单合同补充：`people`、`meal_type`、`stock_mode`、`taste_mode` 四个可见用餐字段必填。隐藏 UUID `request_id` 和 CSRF 继续必需；其他用餐字段可不传或留空，但填值仍校验范围和格式。`max_minutes` 空时存 null，有值为 5–1440 整数；`spice_max` 空时存 null，有值为 0–5 整数；`skill` 空时存空串，有值仍限既有枚举。`must_meet_time=on` 且时间空时返回422并解释冲突。null不等于0；0辣度不得丢失。未填写耗时不加排序惩罚，未填本餐辣度仍遵守已保存限制。旧有值条件继续正常读取，无迁移。外部模型授权仍单独检查，未选器材仍可能没有可执行结果；幂等/对象权限/采购及库存接口保持不变。

以下为登录家庭成员的同源 HTML 页面与表单，不使用 JWT，也不接受浏览器提供的模型 URL。所有 POST 均由 Django CSRF 检查；动态响应 `no-store`。

| 方法与路径 | 行为 |
|---|---|
| `GET/POST /recipes/workbench/` | 输入自然语言或结构化条件；POST 只做有限字面解释，返回可编辑确认页，不写库存 |
| `POST /recipes/workbench/confirm/` | 将确认后的条件按成员和 UUID 幂等保存，跳转候选；条件号与不同条件复用返回 409 |
| `GET /recipes/workbench/{plan_uuid}/` | 仅本人可看；按最新可用库存、硬条件、口味和可追溯营养重新排序；无解时不凑数 |
| `POST /recipes/workbench/{plan_uuid}/menu/` | 选 1–4 道菜谱建立菜单，按统一库存重新分配；浏览与建立菜单均不扣库存 |
| `GET /recipes/workbench/menu/{menu_uuid}/` | 仅本人可看；批次分配、净缺口、营养、参考顺序与确认表单 |
| `POST /recipes/workbench/menu/{menu_uuid}/shopping/` | 选定缺料后可用 `buy_<食材名|单位>` 调整本次计划购买量（缺省为理论净缺口），再显式加入采购；`snapshot` 过期拒绝，同菜单版本同食材和单位的贡献只建一次；有同名库存或待购项须勾选重复确认 |
| `POST /recipes/workbench/menu/{menu_uuid}/cook/` | `snapshot`、UUID `request_id`、`actual_{lot_id}`、`confirm_use=on`；重新核对菜单、批次状态和版本后调用原 `apply_action(cook)`，全餐一次事务，记录流水与按实际量重算的营养；同菜单不得再次执行 |
| `GET/POST /recipes/preferences/` | 个人口味、限制、经历与授权分享设置；仅本人维护，乐观版本检查 |
| `GET/POST /recipes/preferences/household/` | 家庭默认口味；仅管理员可改 |
| `POST /recipes/workbench/{plan_uuid}/feedback/{recipe_id}/` | 本人反馈：喜欢、不喜欢、太辣、太甜、太复杂、愿意再做或清除；浏览不会自动形成反馈 |

生成入口 `POST /recipes/workbench/{plan_uuid}/generate/` 使用 UUID `request_id`；外部提供者还需 `external_consent=on`。未配置模型时返回真实的 503 页面，本地候选仍可用。`GET /recipes/generation/{task_uuid}/`、`GET /recipes/generation/{task_uuid}/status/` 和 `POST .../cancel/`、`POST .../save/` 都只允许任务本人访问。状态接口返回 `{id,status,error_code,result_available}`，状态为 `queued/running/validating/success/failed/cancelled/timed_out`，不提供伪造进度百分比。保存只接受已通过服务端校验的结果，确认保存也不扣库存。工作进程由 `run_recipe_worker` 管理命令提供；默认未启动。

模型输入最小化：本次已确认条件去掉原始文字和成员 ID，可用库存只传食材名、同单位合计数量；不传账号、Cookie、批次备注和完整数据库。固定适配层、系统提示词及 JSON Schema 位于 `meals/generation.py`，服务端结构与教程校验位于 `meals/structured.py`，库存与营养重算位于 `meals/workbench.py`。模型输出即使 JSON 合法也不视为事实或安全认证。应用内任务 UUID 幂等只保证本地重复点击不重复入队；供应商是否已接收不确定时不会无限重试，不能承诺外部绝不重复计费。

## 错误合同

API 错误格式：`{"error":{"code":"机器码","message":"中文说明"}}`。已实现 400 JSON 格式/媒体类型错误、401 未登录、403 无权限/CSRF、404 批次或动作不存在、405 方法不符、409 状态/数量/版本/幂等冲突、422 参数校验、429 登录节流、503 **已确认的**短暂 SQLite 忙（`Retry-After: 2`）、501 预留功能未开放。其他数据库故障仍是脱敏 500，不能误报 503；所有动态响应 `Cache-Control: no-store`。CSRF 拒绝在 API 返回 JSON，在网页返回中文错误页。

## 第三次优化录入合同（2026-10-05）

HTML POST /inventory/ 和 JSON POST /api/inventory/ 可选传 `shelf_life_mode`：

- `date`：用 `package_date`（YYYY-MM-DD 或空）；忽略未选中天数控件的值。
- `days`：同时传 `shelf_life_days`（1–36500 的整数）和 `shelf_life_start`（YYYY-MM-DD）；截止日期=起算日期+天数，超界/缺一项/非法日期返回 422。两项都空表示未知，不使用采购日期推断。
- 显式模式不能另传 `package_date_status`，避免双重合同冲突；适配器算出 known/unknown，再调用原 create_lot。原 API 不传模式的请求合同保持兼容，未知字段仍拒绝。
- 幂等比较基于转换后的规范参数，同编号同日期返回原结果，不同日期 409；日期/天数只是输入方式，只持久保存最终截止日期。
- 添加页四项必填为食材名称、数量、单位、储存位置，另可填计划食用日期、采购日期与保质期。新批次默认储存待核对，编辑页可按事实核对，照片或日期不能自动通过安全状态。
- 列表移至 /inventory/list/；添加、编辑、批次动作的 HTML 成功跳转更新到此处，JSON 成功结构不变。页面浏览和分类过滤没有库存/采购副作用。

## 第二次优化页面合同（2026-10-04，历史）

- 页面层级为 /welcome/ → /login/ 或 /register/ → / → /inventory/、/recipes/、/shopping/。三功能页分别显示添加菜品、查看菜谱、采购计划；左上返回首页，原路由、参数与业务 API 保持兼容。移除路径式标题和旧底部导航，保留步骤/详情的业务返回。
- POST /register/ 新用户名最多 10 字符、密码至少 8 字符；继续检查字符、重名、相似/常见/纯数字密码、邀请码和 CSRF。违反条件返回 422，不创建账号或消费邀请。原长用户名仍可通过 POST /login/ 登录，不修改原账号。
- 登录/注册的眼睛按钮只改变本地输入类型，1 秒后恢复；不提交请求。首页和三功能页浏览不新增库存动作、流水或采购。今日安排仍由 GET /api/today/ 提供。

## 第一次优化接口变更（2026-10-03）

- 未登录 `GET /` 跳转 `/welcome/`，欢迎页提供 `/login/` 与 `/register/`。`POST /register/` 使用 Django UserCreationForm 的 username/password1/password2 与 invitation，需 CSRF、有效管理员邀请码及密码校验。成功在短事务创建普通成员并消费邀请后跳登录，绝不自动注册管理员；无效/已使用/过期邀请码 422。密码不回显、不记录普通日志。
- `GET /settings/` 允许家庭成员查看入口与个人配置链接。仅管理员可 `POST create_invitation=yes`，返回当前页的一次性邀请码，24 小时有效，最多 20 个未过期邀请。邀请码只在该私有响应展示，不放 URL、共享缓存或普通日志。原 `/api/settings/` 管理员权限保留。
- `GET /recipes/` 与 `/api/recipes/` 只包含真实可用库存 `matched_count > 0` 的菜谱。部分材料匹配不等于足量，必要用量仍待确认。`GET /recipes/library/` 保留有权访问的全部本地/家庭收藏浏览与原详情引用。
- `GET /recipes/workbench/?direct=1` 显示“填写菜谱要求”；`POST /recipes/workbench/confirm/` 额外 `generate=yes` 直接确认条件并入队，成功跳任务页，不经过旧候选中间页；同一次条件 UUID 派生固定生成 UUID，刷新/重复提交不重复入队。外部模型仍须 external_consent=on；未配置时明确显示本地降级。旧自然语言解释与候选路由继续兼容。
- `POST /api/inventory/recognize/` 原 image base64 JPEG/PNG/WebP 字段及登录/CSRF/解压上限保留。响应增加 `engine:"yolo"`、最多 10 个去重 candidates，每项 ingredient_name 与 confidence（检测分数）；兼容 ingredient_name，uncertain 始终 true，用户须确认。不写库存、不保存照片，不把物体个数当库存数量。YOLO 未安装、模型校验失败、单槽繁忙分别返回安全 503 代码 recognition_not_configured/recognition_model_invalid/recognition_busy。
