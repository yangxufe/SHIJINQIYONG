"""Ephemeral local YOLO detection; photos never leave this process or persist."""

import base64
import ast
import binascii
import hashlib
import io
import json
import os
import threading
import warnings
from pathlib import Path

import numpy as np
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 2_500_000
MAX_PIXELS = 20_000_000
_INFERENCE_SLOT = threading.BoundedSemaphore(1)
_SESSION = None


class RecognitionError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _normalise_photo(image_b64):
    if not isinstance(image_b64, str) or len(image_b64) > (MAX_IMAGE_BYTES * 4 // 3 + 8):
        raise RecognitionError(422, "invalid_image", "照片过大，请重拍或选择较小的照片。")
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RecognitionError(422, "invalid_image", "照片格式无效。") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise RecognitionError(422, "invalid_image", "照片大小无效。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP"]) as source:
                if source.width * source.height > MAX_PIXELS or min(source.size) < 64:
                    raise RecognitionError(422, "invalid_image", "照片分辨率不合适，请重拍。")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
                # A new RGB image prevents EXIF, GPS and other source metadata passing on.
                clean = Image.new("RGB", oriented.size, "white")
                if oriented.mode == "RGBA":
                    clean.paste(oriented, mask=oriented.getchannel("A"))
                else:
                    clean.paste(oriented.convert("RGB"))
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=82)
                return output.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise RecognitionError(422, "invalid_image", "无法读取这张照片，请使用清晰的 JPG、PNG 或 WebP 照片。") from exc



def _load_detector():
    global _SESSION
    directory = (Path(settings.DATA_DIR) / "models").resolve()
    path = Path(os.environ.get("SHIJIN_YOLO_MODEL", directory / "yolo-food.onnx")).resolve()
    if directory not in path.parents or path.suffix != ".onnx":
        raise RecognitionError(503, "recognition_not_configured", "YOLO 模型路径无效，请联系家庭管理员。")
    if _SESSION is not None and _SESSION[0] == path:
        return _SESSION[1:]
    manifest_path = path.with_suffix(".json")
    try:
        if not path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError
        if path.stat().st_size > 100_000_000 or manifest_path.stat().st_size > 32_000:
            raise ValueError
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        classes = manifest["classes"]
        if manifest.get("schema_version") != 1 or not isinstance(classes, list) or not 1 <= len(classes) <= 100:
            raise ValueError
        for row in classes:
            if set(row) != {"prompt", "name"} or not all(isinstance(value, str) and 1 <= len(value) <= 80 and
                    not any(ord(char) < 32 or char in "<>" for char in value) for value in row.values()):
                raise ValueError
        with path.open("rb") as source:
            digest = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != manifest["sha256"]:
            raise ValueError
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, 640, 640] or inputs[0].type != "tensor(float)":
            raise ValueError
        if len(session.get_outputs()) != 1 or session.get_outputs()[0].shape != [1, 4 + len(classes), 8400]:
            raise ValueError
        names_text = session.get_modelmeta().custom_metadata_map.get("names", "")
        if len(names_text) > 32_000:
            raise ValueError
        if ast.literal_eval(names_text) != {index: row["prompt"] for index, row in enumerate(classes)}:
            raise ValueError
    except (FileNotFoundError, ImportError) as exc:
        raise RecognitionError(503, "recognition_not_configured", "本机 YOLO 模型未安装，请联系管理员或手动填写食材。") from exc
    except Exception as exc:
        raise RecognitionError(503, "recognition_model_invalid", "YOLO 模型校验失败，请联系管理员；仍可手动录入。") from exc
    _SESSION = (path, session, classes)
    return session, classes


def _preprocess(photo):
    with Image.open(io.BytesIO(photo)) as image:
        width, height = image.size
        scale = min(640 / width, 640 / height)
        resized = image.resize((round(width * scale), round(height * scale)), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (640, 640), (114, 114, 114))
        offset = ((640 - resized.width) // 2, (640 - resized.height) // 2)
        canvas.paste(resized, offset)
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    return np.ascontiguousarray(tensor), (width, height, scale, *offset)


def _postprocess(output, classes, transform):
    if output.shape != (1, 4 + len(classes), 8400) or not np.isfinite(output).all():
        raise ValueError("invalid detector output")
    rows = output[0].T
    scores = rows[:, 4:].max(axis=1)
    indices = np.flatnonzero((scores >= .35) & (scores <= 1) & (rows[:, 2] > 0) & (rows[:, 3] > 0))
    indices = indices[np.argsort(-scores[indices], kind="stable")[:300]]
    detections = []
    width, height, scale, offset_x, offset_y = transform
    for index in indices:
        row = rows[index]
        category = int(row[4:].argmax())
        cx, cy, box_w, box_h = row[:4]
        box = np.array([(cx - box_w / 2 - offset_x) / scale, (cy - box_h / 2 - offset_y) / scale,
                        (cx + box_w / 2 - offset_x) / scale, (cy + box_h / 2 - offset_y) / scale])
        box[[0, 2]] = np.clip(box[[0, 2]], 0, width)
        box[[1, 3]] = np.clip(box[[1, 3]], 0, height)
        area = (box[2] - box[0]) * (box[3] - box[1])
        if area <= 0:
            continue
        overlap = False
        for existing in detections:
            old = np.array(existing["pixel_box"])
            intersection = np.prod(np.maximum(0, np.minimum(box[2:], old[2:]) - np.maximum(box[:2], old[:2])))
            union = area + (old[2]-old[0]) * (old[3]-old[1]) - intersection
            # Class-agnostic NMS avoids labeling the same visible food several ways.
            if intersection / max(union, 1e-6) > .45:
                overlap = True
                break
        if overlap:
            continue
        detections.append({"ingredient_name": classes[category]["name"], "confidence": round(float(scores[index]), 3),
                           "pixel_box": box.tolist()})
        if len(detections) == 10:
            break
    candidates = []
    for detection in detections:
        if detection["ingredient_name"] not in [item["ingredient_name"] for item in candidates]:
            candidates.append({key: value for key, value in detection.items() if key != "pixel_box"})
    return {"ingredient_name": candidates[0]["ingredient_name"] if candidates else "",
            "uncertain": True, "engine": "yolo", "candidates": candidates}


def _detect(photo):
    session, classes = _load_detector()
    tensor, transform = _preprocess(photo)
    try:
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        return _postprocess(output, classes, transform)
    except Exception as exc:
        raise RecognitionError(503, "recognition_failed", "YOLO 识别未完成，请重拍或手动填写名称。") from exc


def recognise(image_b64):
    photo = _normalise_photo(image_b64)
    if not _INFERENCE_SLOT.acquire(blocking=False):
        raise RecognitionError(503, "recognition_busy", "正在识别另一张照片，请稍后重试。")
    try:
        return _detect(photo)
    finally:
        _INFERENCE_SLOT.release()
