# 食材 YOLO 模型

`yolo-food.onnx` 为官方 `yolov8s-worldv2.pt` 的固定词表 ONNX 导出，使用 `scripts/export_yolo_food.py` 构建；32 个食材提示词来自 `inventory/yolo_classes.json`，不是用家庭照片训练的专用模型。

模型 SHA-256：`bb695271871958cd380ff911888aeed8867ceb24071933efc26b337639e78f41`。来源、原始权重校验和、中文映射在 `yolo-food.json`。`scripts/install_yolo_food.py` 从仓库复制并验证模型到私有 `data/models/`，运行期间不下载权重、不发送照片。

上游软件与官方模型按 AGPL-3.0 或另行取得的企业许可使用；模型及导出版本附上游 AGPL 全文 `LICENSE-AGPL-3.0.txt`。参见 [Ultralytics 模型授权说明](https://www.ultralytics.com/license)和 [YOLO-World 说明](https://docs.ultralytics.com/models/yolo-world/)。此文件说明该第三方模型的许可证，不替仓库所有者决定其他自写代码的许可。

不是食材安全模型，也不是 OCR。未验证所有 32 类的识别准确率；遮挡、光照、相似肉类、不透明包装可能未检出或误认。候选分数是检测器分数，不能当成准确率、安全程度、数量或保质期。
