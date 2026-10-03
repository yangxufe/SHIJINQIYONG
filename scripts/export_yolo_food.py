"""Explicit build step; only official weights, never user supplied checkpoints."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt"


def main():
    build = ROOT / "work" / "yolo-build"
    build.mkdir(parents=True, exist_ok=True)
    weights = build / "yolov8s-worldv2.pt"
    if not weights.is_file():
        request = urllib.request.Request(WEIGHTS_URL, headers={"User-Agent": "ShiJinQiYong-YOLO-setup"})
        temporary = weights.with_suffix(".download")
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as destination:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 100_000_000:
                    raise ValueError("Oversized official weights")
                destination.write(chunk)
        temporary.replace(weights)
    # Ultralytics builds its fixed vocabulary with CLIP once; no text model at runtime.
    configuration = build / "ultralytics-config"
    configuration.mkdir(exist_ok=True)
    os.environ["YOLO_CONFIG_DIR"] = str(configuration)
    os.chdir(build)
    from ultralytics import YOLOWorld
    classes = json.loads((ROOT / "inventory" / "yolo_classes.json").read_text(encoding="utf-8"))
    model = YOLOWorld(str(weights))
    model.set_classes([row["prompt"] for row in classes])
    model.model.eval()
    exported = Path(model.export(format="onnx", imgsz=640, dynamic=False, simplify=False,
                                 opset=17, nms=False, device="cpu", batch=1))
    destination = ROOT / "data" / "models"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "yolo-food.onnx"
    shutil.copyfile(exported, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "model": "yolov8s-worldv2", "classes": classes,
                "sha256": digest, "weights_source": WEIGHTS_URL, "license": "AGPL-3.0",
                "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest()}
    target.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("YOLO export complete; sha256=" + digest)


if __name__ == "__main__":
    main()
