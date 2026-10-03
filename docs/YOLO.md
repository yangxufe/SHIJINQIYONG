# 本机 YOLO 食材检测

## 更新后启用（Windows / macOS）

先停止 Waitress，更新仓库并按原系统教程安装 requirements.lock、执行兼容迁移和 collectstatic。Windows 在项目目录运行：

```powershell
& scripts/stop_waitress_for_backup.ps1
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock
& scripts/manage_prod.ps1 migrate --noinput
& scripts/manage_prod.ps1 collectstatic --noinput
& .\.venv\Scripts\python.exe scripts/install_yolo_food.py
Start-ScheduledTask ShiJinQiYong-Waitress
```

macOS 已按 MACOS.md 初始化后运行：

```bash
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/macos_runtime.py manage migrate --noinput
.venv/bin/python scripts/macos_runtime.py manage collectstatic --noinput
.venv/bin/python scripts/install_yolo_food.py
.venv/bin/python scripts/macos_runtime.py waitress
```

若原运行配置自定义了 SHIJIN_DATA_DIR，安装命令必须追加 `--data-dir <同一私有数据目录>`；不要装到另一个目录。默认安装到本项目 data/models/yolo-food.onnx 和 yolo-food.json。没有联网下载步骤，仓库已附 51,287,685 字节 ONNX 和完整类序/散列清单；第一次加载较慢，后续复用进程内会话。已有不同模型时安装脚本拒绝覆盖，先停服务并备份它再人工处理。

Windows 停止脚本必须成功后再继续；它会核对并清理 venv 启动器留下的 Waitress 基础解释器子进程。只停止计划任务可能仍留下旧模型会话与旧代码；重启后检查健康页，不以任务 Running 代替验收。

在冰箱选择“拍照”或“相册”，选择清晰食材照片，等待真实候选；点击确认后仅填入名称，数量仍为空，填写实际数量、状态和储存信息后显式保存。方框其他位置不打开选择器。capture 是浏览器相机提示，Android 系统相机/相册具体行为须现场核验；电脑打开文件选择器不等于手机相机已经测试。

食品照片不再调用 qwen3-vl:8b 或 Ollama；无需启动视觉模型服务。旧 Ollama 启动脚本保留供可选菜谱提供者使用，新登录任务脚本仅注册 Waitress。没有配置菜谱提供者时，“生成个性化菜谱”诚实降级为本地匹配，并未调用真实菜谱生成模型。

## 模型与边界

官方 [YOLO-World v2](https://docs.ultralytics.com/models/yolo-world/)小型权重，在构建时固定 32 个英文食材提示词与中文名称。生产只有 [ONNX Runtime CPU 推理](https://onnxruntime.ai/docs/api/python/api_summary.html)，两线程、单并发；输入 1×3×640×640，输出 1×36×8400，检测阈值 0.35，类别无关 NMS 0.45，最多 10 个去重候选。默认词表及上游许可见 model_assets/README.md。

加载前检查散列、图像尺寸、类序、张量形状；图片最大 2.5 MB、2,000 万像素，重新编码去元数据，不存照片。模型路径只能为 data/models 下本机 ONNX，不接受浏览器模型 URL。管理员自定义 SHIJIN_YOLO_MODEL 时须给出相同输入/输出协议及同名 .json 清单；不支持任意 .pt 或旧 YOLOv5 带 objectness 张量。更换后重启 Waitress，不在请求期间热替换。

开放词表不等于完成专用食材训练。尚无全 32 类准确率验证，也未核验家庭照片。肉类外观相似、遮挡、熟菜和不透明包装可能漏检/误认。YOLO 不做包装 OCR；看不见实物时手工填写包装上的名称和日期。检测分数不代表正确概率或食品安全，不推断重量、数量、新鲜度和保质期。

## 实际验证（2026-10-03）

- 已真实从官方权重导出 ONNX，SHA-256 为 bb695271871958cd380ff911888aeed8867ceb24071933efc26b337639e78f41。原权重来源与散列在清单。
- 实际推理空白图无候选。公开 [COCO128 样本包](https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip) 4 张样本：000000000370 检出西兰花 0.634；000000000196 未检出；000000000009 检出西兰花 0.721 和需人工核对的橙子 0.360；000000000584 未检出。没有隐去失败样本或把它们称为识别全通过。浏览器经重编码的第一张样本分数约 0.62。
- 真实浏览器相册上传公开样本，出现候选，确认前名称为空，确认后数量仍为空且库存仍 0；未上传家庭照片。桌面相机按钮触发独立文件选择器，无法替代 Android 原生相机测试。
- 自动化测试仅用明确标记的模拟检测结果校验鉴权/CSRF与无库存副作用，另有真实预处理/NMS、缺模型、散列安装防覆盖测试。它们不证明所有食品准确率。
- 并行真实推理性能见 PERFORMANCE.md；普通业务数量事务和幂等未改变。

## 重新构建（维护者可选）

日常运行无需安装 PyTorch/Ultralytics/CLIP。需要改词表再构建时，在独立临时虚拟环境安装已核验版本：Ultralytics 8.4.171、torch 2.9.1+cpu / torchvision 0.24.1+cpu（Windows CPU 官方轮子）、onnx 1.19.1；CLIP 构建采用官方 Ultralytics/CLIP 提交 a13192f8cb767260d7dfd98c843b0716593169e7。执行 scripts/export_yolo_food.py，记录新散列并更新模型资产与清单；不要把临时环境、CLIP 缓存或真实训练照片提交仓库。macOS 构建依赖应另行按官方 PyTorch 平台轮子核验，不能照抄 Windows CPU 包索引假称已测试。

上游 [模型许可](https://www.ultralytics.com/license)为 AGPL-3.0 或另行取得的企业许可；附上游 AGPL 全文。没有替作者决定其他代码的许可。
