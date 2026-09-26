"""Private recipe images and videos, stored outside Caddy's static tree."""

import hashlib
import io
import os
import re
import tempfile
import unicodedata
import warnings
from pathlib import Path
from uuid import UUID, uuid4

from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from inventory import services as inventory_service
from meals.models import RecipeMedia


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
FILE_KEY_PATTERN = re.compile(r"[0-9a-f]{32}\.(?:jpg|mp4|webm|mov)\Z")


def media_root():
    return settings.DATA_DIR / "recipe_media"


def media_path(item):
    if not FILE_KEY_PATTERN.fullmatch(item.file_key):
        raise ValueError("Invalid private media key")
    return media_root() / item.file_key


def _caption(value):
    if not isinstance(value, str):
        raise inventory_service.InventoryError(422, "invalid_input", "图片或视频说明无效。")
    value = unicodedata.normalize("NFC", value.strip())
    if len(value) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise inventory_service.InventoryError(422, "invalid_input", "图片或视频说明过长或包含不支持的字符。")
    return value


def _image_bytes(upload):
    raw = upload.read(MAX_IMAGE_BYTES + 1)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise inventory_service.InventoryError(422, "invalid_image", "图片不能超过 8 MB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP"]) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise inventory_service.InventoryError(422, "invalid_image", "图片像素过多。")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                clean = Image.new("RGB", oriented.size, "white")
                if oriented.mode == "RGBA":
                    clean.paste(oriented, mask=oriented.getchannel("A"))
                else:
                    clean.paste(oriented.convert("RGB"))
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=84)
                return output.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise inventory_service.InventoryError(422, "invalid_image", "无法读取图片，请使用 JPG、PNG 或 WebP。") from exc


def _video_type(upload):
    suffix = Path(upload.name).suffix.lower()
    header = upload.read(16)
    upload.seek(0)
    if suffix in {".mp4", ".mov"} and len(header) >= 12 and header[4:8] == b"ftyp":
        return suffix, "video/mp4" if suffix == ".mp4" else "video/quicktime"
    if suffix == ".webm" and header.startswith(b"\x1a\x45\xdf\xa3"):
        return suffix, "video/webm"
    raise inventory_service.InventoryError(422, "invalid_video", "视频请使用 MP4、MOV 或 WebM 文件。")


def save_upload(actor, recipe, upload, *, kind, caption, request_id):
    inventory_service._require_member(actor)
    if kind not in {RecipeMedia.Kind.IMAGE, RecipeMedia.Kind.VIDEO} or upload is None:
        raise inventory_service.InventoryError(422, "invalid_input", "请选择图片或视频文件。")
    caption = _caption(caption)
    try:
        request_id = UUID(str(request_id))
    except (TypeError, ValueError) as exc:
        raise inventory_service.InventoryError(422, "invalid_input", "上传请求编号无效。") from exc
    if kind == RecipeMedia.Kind.IMAGE:
        body = _image_bytes(upload)
        suffix, mime_type, maximum = ".jpg", "image/jpeg", MAX_IMAGE_BYTES
    else:
        suffix, mime_type = _video_type(upload)
        body = None
        maximum = MAX_VIDEO_BYTES
    if upload.size and upload.size > maximum:
        raise inventory_service.InventoryError(422, "file_too_large", "文件超过当前上传上限。")
    root = media_root()
    root.mkdir(parents=True, exist_ok=True)
    temporary = None
    destination = None
    committed = False
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix="upload-", suffix=".tmp", delete=False) as sink:
            temporary = Path(sink.name)
            chunks = [body] if body is not None else upload.chunks(chunk_size=1024 * 1024)
            for chunk in chunks:
                size += len(chunk)
                if size > maximum:
                    raise inventory_service.InventoryError(422, "file_too_large", "文件超过当前上传上限。")
                digest.update(chunk)
                sink.write(chunk)
        if not size:
            raise inventory_service.InventoryError(422, "invalid_input", "不能上传空文件。")
        sha256 = digest.hexdigest()
        with transaction.atomic():
            original = RecipeMedia.objects.filter(created_by=actor, upload_request_id=request_id).first()
            if original is not None:
                if original.recipe_id != recipe.pk or original.kind != kind or original.sha256 != sha256 or original.caption != caption:
                    raise inventory_service.InventoryError(409, "idempotency_conflict", "该上传编号已用于其他文件或说明。")
                result = original
            else:
                if kind == RecipeMedia.Kind.VIDEO and RecipeMedia.objects.filter(recipe=recipe, kind="video").exists():
                    raise inventory_service.InventoryError(409, "video_exists", "这道菜已有一个本机视频，请先删除旧视频。")
                if kind == RecipeMedia.Kind.IMAGE and RecipeMedia.objects.filter(recipe=recipe, kind="image").count() >= 6:
                    raise inventory_service.InventoryError(422, "image_limit", "每道菜最多保存 6 张图片。")
                file_key = uuid4().hex + suffix
                destination = root / file_key
                os.replace(temporary, destination)
                temporary = None
                result = RecipeMedia.objects.create(
                    recipe=recipe, kind=kind, file_key=file_key, mime_type=mime_type,
                    size_bytes=size, caption=caption, created_by=actor,
                    upload_request_id=request_id, sha256=sha256,
                )
        committed = True
        return result
    except OperationalError as exc:
        if inventory_service._is_busy(exc):
            raise inventory_service.InventoryError(503, "database_busy", "数据库暂时繁忙，请保留原编号重试。") from exc
        raise
    except IntegrityError as exc:
        raise inventory_service.InventoryError(409, "upload_conflict", "上传状态已变化，请刷新后重试。") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if destination is not None and not committed:
            destination.unlink(missing_ok=True)


def delete_upload(actor, recipe, item):
    inventory_service._require_member(actor)
    if item.recipe_id != recipe.pk:
        raise inventory_service.InventoryError(404, "not_found", "附件不存在。")
    path = media_path(item)
    item.delete()
    path.unlink(missing_ok=True)
