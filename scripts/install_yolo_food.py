"""Install the shipped, checksummed public ONNX model; no runtime network calls."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install(data_dir):
    source = ROOT / "model_assets" / "yolo-food.onnx"
    manifest = ROOT / "model_assets" / "yolo-food.json"
    expected = json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
    if sha256(source) != expected:
        raise ValueError("仓库中的 YOLO 模型校验失败，请重新下载完整仓库。")
    destination = Path(data_dir).resolve() / "models"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / source.name
    if target.exists() and sha256(target) != expected:
        raise ValueError("已有不同的 YOLO 模型。请先停止应用并备份原模型，再人工移出旧文件后安装。")
    if not target.exists():
        temporary = target.with_suffix(".installing")
        shutil.copyfile(source, temporary)
        if sha256(temporary) != expected:
            raise ValueError("模型复制校验失败。")
        temporary.replace(target)
    shutil.copyfile(manifest, destination / manifest.name)
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("SHIJIN_DATA_DIR", ROOT / "data")))
    args = parser.parse_args()
    try:
        digest = install(args.data_dir)
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    print("本机 YOLO 模型已安装并校验。sha256=" + digest)


if __name__ == "__main__":
    main()
