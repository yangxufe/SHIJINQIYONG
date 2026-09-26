"""Inventory writes: one short SQLite transaction per durable business action."""

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.core.paginator import InvalidPage, Paginator
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q
from django.utils import timezone

from core.security import has_role
from inventory.availability import household_today
from inventory.models import BusinessAction, Ingredient, InventoryLot, Movement


MAX_MILLI = 1_000_000_000_000
AMOUNT_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,3})?\Z")
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
UNITS = set(InventoryLot.Unit.values)
LOCATIONS = set(InventoryLot.Location.values)


class InventoryError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _fail(message, code="invalid_input", status=422):
    raise InventoryError(status, code, message)


def _require_member(actor):
    if not (has_role(actor, "member") or has_role(actor, "admin")):
        raise InventoryError(403, "forbidden", "当前账号无权操作库存。")


def _object(value):
    if not isinstance(value, dict):
        _fail("请求必须是对象。")
    return value


def _keys(payload, allowed):
    unknown = set(payload) - set(allowed)
    if unknown:
        _fail("包含不支持的字段。")


def _text(value, label, maximum, required=True):
    if not isinstance(value, str):
        _fail(f"{label}必须是文本。")
    value = unicodedata.normalize("NFC", value.strip())
    if (required and not value) or len(value) > maximum or CONTROL_PATTERN.search(value):
        _fail(f"{label}长度或内容无效。")
    return value


def _choice(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        _fail(f"{label}无效。")
    return value


def _integer(value, label, minimum=0, maximum=2_147_483_647):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        _fail(f"{label}必须是整数。")
    if isinstance(value, str):
        if len(value) > 10 or not re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
            _fail(f"{label}必须是整数。")
        value = int(value)
    if not minimum <= value <= maximum:
        _fail(f"{label}越界。")
    return value


def _boolean(value, label):
    if isinstance(value, bool):
        return value
    if value in ("true", "false"):
        return value == "true"
    _fail(f"{label}必须是真或假。")


def parse_amount(value, *, allow_zero=False):
    """Only finite decimal strings with <=3 places become fixed-scale integers."""
    if not isinstance(value, str) or len(value) > 16 or not AMOUNT_PATTERN.fullmatch(value):
        _fail("数量必须是最多三位小数的非负十进制字符串。")
    milli = int(Decimal(value) * 1000)
    if milli > MAX_MILLI or (milli == 0 and not allow_zero):
        _fail("数量为零或超出范围。")
    return milli


def format_amount(milli):
    whole, fraction = divmod(abs(milli), 1000)
    sign = "-" if milli < 0 else ""
    return f"{sign}{whole}" + (f".{fraction:03d}".rstrip("0") if fraction else "")


def _date(value, label):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        _fail(f"{label}必须是 YYYY-MM-DD 日期。")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        _fail(f"{label}不是有效日期。")


def _request_id(value):
    if not isinstance(value, str) or len(value) > 36:
        _fail("请求编号必须是 UUID。")
    try:
        return str(UUID(value))
    except ValueError:
        _fail("请求编号必须是 UUID。")


def _package_consistent(fields):
    known = fields["package_date_status"] == "known"
    if known != (fields["package_date"] is not None):
        _fail("包装日期状态与日期不一致。")


def _lot_dict(lot):
    return {
        "id": lot.pk,
        "ingredient_name": lot.ingredient.name,
        "name": lot.name,
        "quantity": format_amount(lot.quantity_milli),
        "unit": lot.unit,
        "unit_label": lot.get_unit_display(),
        "location": lot.location,
        "location_label": lot.get_location_display(),
        "planned_use_date": lot.planned_use_date.isoformat() if lot.planned_use_date else None,
        "package_date": lot.package_date.isoformat() if lot.package_date else None,
        "package_date_text": lot.package_date_text,
        "package_date_status": lot.package_date_status,
        "package_date_status_label": lot.get_package_date_status_display(),
        "purchase_date": lot.purchase_date.isoformat() if lot.purchase_date else None,
        "opened_date": lot.opened_date.isoformat() if lot.opened_date else None,
        "status": lot.status,
        "status_label": lot.get_status_display(),
        "storage_status": lot.storage_status,
        "storage_status_label": lot.get_storage_status_display(),
        "manual_priority": lot.manual_priority,
        "version": lot.version,
        "created_at": lot.created_at.isoformat(),
        "updated_at": lot.updated_at.isoformat(),
        "updated_at_label": timezone.localtime(lot.updated_at).strftime("%Y-%m-%d %H:%M"),
    }


def _digest(kind, normalized):
    encoded = json.dumps({"kind": kind, "payload": normalized}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _existing(actor, request_id, kind, digest):
    action = BusinessAction.objects.filter(actor=actor, request_id=request_id).first()
    if action is None:
        return None
    if action.kind != kind or action.params_hash != digest:
        raise InventoryError(409, "idempotency_conflict", "该请求编号已用于其他参数。")
    return action.result


def _is_busy(exc):
    cause = exc.__cause__
    if not isinstance(cause, sqlite3.OperationalError):
        return False
    code = getattr(cause, "sqlite_errorcode", None)
    if isinstance(code, int):
        return code & 0xFF in {5, 6}  # SQLITE_BUSY / SQLITE_LOCKED
    return str(cause).lower() in {"database is locked", "database table is locked", "database schema is locked"}


def _execute(actor, request_id, kind, normalized, work):
    digest = _digest(kind, normalized)
    try:
        _require_member(actor)
        with transaction.atomic():
            original = _existing(actor, request_id, kind, digest)
            if original is not None:
                return original
            action = BusinessAction.objects.create(actor=actor, request_id=request_id, kind=kind, params_hash=digest, result={})
            status, body = work(action)
            body = {"action_id": action.pk, "request_id": request_id, **body}
            action.result = {"status": status, "body": body}
            action.save(update_fields=["result"])
            return action.result
    except OperationalError as exc:
        if _is_busy(exc):
            raise InventoryError(503, "database_busy", "数据库暂时繁忙，请用同一请求编号重试。") from exc
        raise
    except IntegrityError as exc:
        # Only a request-key collision can be retried. Query after atomic rolled back.
        if "inventory_businessaction.actor_id, inventory_businessaction.request_id" in str(exc):
            original = _existing(actor, request_id, kind, digest)
            if original is not None:
                return original
        raise


def create_lot(actor, payload):
    payload = _object(payload)
    _keys(payload, {"request_id", "ingredient_name", "name", "quantity", "unit", "location", "planned_use_date", "package_date", "package_date_text", "package_date_status", "purchase_date", "opened_date", "status", "storage_status", "manual_priority"})
    request_id = _request_id(payload.get("request_id"))
    ingredient_name = _text(payload.get("ingredient_name"), "食材名称", 80)
    normalized = {
        "ingredient_name": ingredient_name,
        "name": _text(payload.get("name") or ingredient_name, "批次名称", 80),
        "quantity_milli": parse_amount(payload.get("quantity")),
        "unit": _choice(payload.get("unit"), UNITS, "单位"),
        "location": _choice(payload.get("location"), LOCATIONS, "位置"),
        "planned_use_date": _date(payload.get("planned_use_date"), "计划日期"),
        "package_date": _date(payload.get("package_date"), "包装日期"),
        "package_date_text": _text(payload.get("package_date_text", ""), "包装日期原文", 80, required=False),
        "package_date_status": _choice(payload.get("package_date_status", "unknown"), set(InventoryLot.PackageDateStatus.values), "包装日期状态"),
        "purchase_date": _date(payload.get("purchase_date"), "采购日期"),
        "opened_date": _date(payload.get("opened_date"), "开封日期"),
        "status": _choice(payload.get("status", "active"), {"active", "suspect"}, "批次状态"),
        "storage_status": _choice(payload.get("storage_status", "needs_check"), set(InventoryLot.StorageStatus.values), "储存状态"),
        "manual_priority": _boolean(payload.get("manual_priority", False), "手动优先"),
    }
    _package_consistent(normalized)

    def work(action):
        ingredient, _ = Ingredient.objects.get_or_create(name=normalized["ingredient_name"])
        lot = InventoryLot.objects.create(ingredient=ingredient, **{key: value for key, value in normalized.items() if key != "ingredient_name"})
        Movement.objects.create(lot=lot, action=action, delta_milli=lot.quantity_milli, unit=lot.unit, before_milli=0, after_milli=lot.quantity_milli)
        lot.refresh_from_db()
        return 201, {"lot": _lot_dict(lot)}

    return _execute(actor, request_id, "lot_create", normalized, work)


EDITABLE = {"name", "location", "planned_use_date", "package_date", "package_date_text", "package_date_status", "purchase_date", "opened_date", "status", "storage_status", "manual_priority"}


def edit_lot(actor, lot_id, payload):
    payload = _object(payload)
    _keys(payload, EDITABLE | {"request_id", "version"})
    request_id = _request_id(payload.get("request_id"))
    lot_id = _integer(lot_id, "批次编号", 1)
    version = _integer(payload.get("version"), "版本号")
    if not (set(payload) & EDITABLE):
        _fail("至少提供一个可编辑字段。")
    patch = {}
    for key in EDITABLE & set(payload):
        value = payload[key]
        if key in {"planned_use_date", "package_date", "purchase_date", "opened_date"}:
            patch[key] = _date(value, key)
        elif key == "name":
            patch[key] = _text(value, "批次名称", 80)
        elif key == "package_date_text":
            patch[key] = _text(value, "包装日期原文", 80, required=False)
        elif key == "location":
            patch[key] = _choice(value, LOCATIONS, "位置")
        elif key == "status":
            patch[key] = _choice(value, {"active", "suspect"}, "批次状态")
        elif key == "storage_status":
            patch[key] = _choice(value, set(InventoryLot.StorageStatus.values), "储存状态")
        elif key == "manual_priority":
            patch[key] = _boolean(value, "手动优先")
        else:
            patch[key] = _choice(value, set(InventoryLot.PackageDateStatus.values), "包装日期状态")
    normalized = {"lot_id": lot_id, "version": version, "patch": patch}

    def work(action):
        try:
            lot = InventoryLot.objects.select_related("ingredient").get(pk=lot_id)
        except InventoryLot.DoesNotExist:
            raise InventoryError(404, "not_found", "批次不存在。")
        if lot.version != version or lot.status in {"discarded", "depleted"}:
            raise InventoryError(409, "version_conflict", "批次已变化，请刷新后重试。")
        if lot.status == "suspect" and patch.get("status") == "active":
            raise InventoryError(409, "needs_review", "疑似变质状态不能通过普通编辑解除。")
        merged = {"package_date_status": patch.get("package_date_status", lot.package_date_status), "package_date": patch.get("package_date", lot.package_date.isoformat() if lot.package_date else None)}
        _package_consistent(merged)
        affected = InventoryLot.objects.filter(pk=lot_id, version=version, status__in=["active", "suspect"]).update(**patch, version=F("version") + 1, updated_at=timezone.now())
        if affected != 1:
            raise InventoryError(409, "version_conflict", "批次已变化，请刷新后重试。")
        lot.refresh_from_db()
        return 200, {"lot": _lot_dict(lot)}

    return _execute(actor, request_id, "lot_edit", normalized, work)


def apply_action(actor, payload):
    payload = _object(payload)
    _keys(payload, {"request_id", "kind", "items", "note"})
    request_id = _request_id(payload.get("request_id"))
    kind = _choice(payload.get("kind"), {"cook", "eat", "discard", "correct"}, "动作类型")
    note = _text(payload.get("note", ""), "说明", 200, required=(kind == "correct"))
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        _fail("每次应提交 1 至 20 个批次。")
    normalized_items = []
    seen = set()
    for item in items:
        item = _object(item)
        _keys(item, {"lot_id", "version", "quantity", "unit"})
        lot_id = _integer(item.get("lot_id"), "批次编号", 1)
        if lot_id in seen:
            _fail("同一请求不能重复提交相同批次。")
        seen.add(lot_id)
        normalized_items.append({"lot_id": lot_id, "version": _integer(item.get("version"), "版本号"), "quantity_milli": parse_amount(item.get("quantity"), allow_zero=(kind == "correct")), "unit": _choice(item.get("unit"), UNITS, "单位")})
    normalized_items.sort(key=lambda item: item["lot_id"])
    normalized = {"items": normalized_items, "note": note}

    def work(action):
        results = []
        day = household_today()[0] if kind in {"cook", "eat"} else None
        for item in normalized_items:
            try:
                lot = InventoryLot.objects.get(pk=item["lot_id"])
            except InventoryLot.DoesNotExist:
                raise InventoryError(404, "not_found", "批次不存在。")
            if lot.version != item["version"] or lot.status in {"discarded", "depleted"}:
                raise InventoryError(409, "version_conflict", "批次已变化，请刷新后重试。")
            if item["unit"] != lot.unit:
                raise InventoryError(409, "unit_conflict", "单位与批次不一致；应用不会猜测换算。")
            if kind in {"cook", "eat"}:
                if lot.status != "active" or lot.storage_status != "verified" or (lot.package_date_status == "known" and lot.package_date < day):
                    raise InventoryError(409, "needs_review", "该批次状态或包装日期需要核对，不能作为可用食材。")
            before = lot.quantity_milli
            if kind == "correct":
                after = item["quantity_milli"]
                delta = after - before
                if delta == 0:
                    _fail("校正后的数量与当前数量相同。")
            else:
                delta = -item["quantity_milli"]
                after = before + delta
                if after < 0:
                    raise InventoryError(409, "insufficient_quantity", "批次数量不足。")
            status = ("discarded" if kind == "discard" else "depleted") if after == 0 else lot.status
            affected = InventoryLot.objects.filter(pk=lot.pk, version=lot.version, quantity_milli=before, status=lot.status, quantity_milli__gte=(-delta if delta < 0 else 0)).update(quantity_milli=F("quantity_milli") + delta, version=F("version") + 1, status=status, updated_at=timezone.now())
            if affected != 1:
                raise InventoryError(409, "version_conflict", "批次已变化，请刷新后重试。")
            Movement.objects.create(lot=lot, action=action, delta_milli=delta, unit=lot.unit, before_milli=before, after_milli=after)
            results.append({"lot_id": lot.pk, "before": format_amount(before), "change": format_amount(delta), "after": format_amount(after), "unit": lot.unit, "status": status, "version": lot.version + 1})
        return 200, {"kind": kind, "note": note, "items": results}

    return _execute(actor, request_id, kind, normalized, work)


def get_action(actor, action_id):
    _require_member(actor)
    action_id = _integer(action_id, "动作编号", 1)
    try:
        return BusinessAction.objects.get(pk=action_id, actor=actor).result
    except BusinessAction.DoesNotExist:
        raise InventoryError(404, "not_found", "动作不存在。")


def get_action_by_request(actor, request_id):
    _require_member(actor)
    request_id = _request_id(request_id)
    try:
        return BusinessAction.objects.get(actor=actor, request_id=request_id).result
    except BusinessAction.DoesNotExist:
        raise InventoryError(404, "not_found", "该请求编号尚无已提交结果。")


def get_lot(actor, lot_id):
    _require_member(actor)
    lot_id = _integer(lot_id, "批次编号", 1)
    try:
        return _lot_dict(InventoryLot.objects.select_related("ingredient").get(pk=lot_id))
    except InventoryLot.DoesNotExist:
        raise InventoryError(404, "not_found", "批次不存在。")


def _page(queryset, page, per_page):
    page = _integer(page, "页码", 1, 1_000_000)
    per_page = _integer(per_page, "每页数量", 1, 100)
    paginator = Paginator(queryset, per_page)
    try:
        result = paginator.page(page)
    except InvalidPage:
        raise InventoryError(404, "not_found", "该页不存在。")
    return result


def list_lots(actor, page=1, per_page=50, query=""):
    _require_member(actor)
    query = _text(query, "搜索词", 80, required=False)
    queryset = InventoryLot.objects.select_related("ingredient")
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(ingredient__name__icontains=query))
    result = _page(queryset.order_by("-updated_at", "-id"), page, per_page)
    return {"page": result.number, "pages": result.paginator.num_pages, "count": result.paginator.count, "query": query, "items": [_lot_dict(lot) for lot in result]}


def list_movements(actor, page=1, per_page=50):
    _require_member(actor)
    result = _page(Movement.objects.select_related("lot", "action", "action__actor").order_by("-created_at", "-id"), page, per_page)
    return {"page": result.number, "pages": result.paginator.num_pages, "count": result.paginator.count, "items": [{"id": movement.pk, "lot_id": movement.lot_id, "action_id": movement.action_id, "kind": movement.action.kind, "actor": movement.action.actor.username, "change": format_amount(movement.delta_milli), "before": format_amount(movement.before_milli), "after": format_amount(movement.after_milli), "unit": movement.unit, "created_at": movement.created_at.isoformat()} for movement in result]}
