"""Shopping state transitions and exactly-once receipt into inventory."""

from django.db.models import F
from django.utils import timezone

from inventory import services as stock
from inventory.availability import household_today, usable_lots
from inventory.models import Ingredient, InventoryLot, Movement
from meals.catalog import load_catalog
from shopping.models import ShoppingItem


def _canonical(name):
    return load_catalog()[1].get(name, name)


def _item_dict(item):
    return {
        "id": item.pk, "name": item.name, "quantity": stock.format_amount(item.quantity_milli),
        "unit": item.unit, "unit_label": item.get_unit_display(),
        "status": item.status, "status_label": item.get_status_display(),
        "version": item.version, "received_lot_id": item.received_lot_id,
        "created_at": item.created_at.isoformat(),
    }


def _overlap(name):
    canonical = _canonical(name)
    existing = []
    safe_lots = list(usable_lots())
    safe_ids = {lot.pk for lot in safe_lots}
    for lot in safe_lots:
        if _canonical(lot.ingredient.name) == canonical:
            existing.append({"quantity": stock.format_amount(lot.quantity_milli), "unit": lot.get_unit_display()})
    needs_review = sum(
        lot.pk not in safe_ids and _canonical(lot.ingredient.name) == canonical
        for lot in InventoryLot.objects.select_related("ingredient").filter(quantity_milli__gt=0, status__in=["active", "suspect"])
    )
    pending = [
        {"id": item.pk, "quantity": stock.format_amount(item.quantity_milli), "unit": item.get_unit_display(), "status": item.get_status_display()}
        for item in ShoppingItem.objects.filter(ingredient__name=canonical, status__in=["needed", "bought"]).order_by("id")[:20]
    ]
    return existing[:20], pending, needs_review


def list_items(actor):
    stock._require_member(actor)
    open_items = ShoppingItem.objects.filter(status__in=["needed", "bought"]).order_by("created_at", "id")
    history = ShoppingItem.objects.filter(status__in=["received", "cancelled"]).order_by("-updated_at", "-id")[:20]
    summaries = {}
    for lot in usable_lots():
        key = (_canonical(lot.ingredient.name), lot.unit)
        summaries[key] = summaries.get(key, 0) + lot.quantity_milli
    available = [
        {"name": name, "quantity": stock.format_amount(quantity), "unit": unit, "unit_label": InventoryLot.Unit(unit).label}
        for (name, unit), quantity in sorted(summaries.items())
    ]
    return {"open": [_item_dict(item) for item in open_items[:100]], "open_count": open_items.count(),
            "history": [_item_dict(item) for item in history], "available": available,
            "available_count": len(available)}


def add_item(actor, payload):
    payload = stock._object(payload)
    stock._keys(payload, {"request_id", "name", "quantity", "unit", "confirm_duplicate"})
    request_id = stock._request_id(payload.get("request_id"))
    name = stock._text(payload.get("name"), "食材名称", 80)
    normalized = {"name": name, "canonical_name": _canonical(name),
                  "quantity_milli": stock.parse_amount(payload.get("quantity")),
                  "unit": stock._choice(payload.get("unit"), stock.UNITS, "单位"),
                  "confirm_duplicate": stock._boolean(payload.get("confirm_duplicate", False), "重复采购确认")}

    def work(action):
        existing, pending, needs_review = _overlap(name)
        if (existing or pending or needs_review) and not normalized["confirm_duplicate"]:
            raise stock.InventoryError(409, "possible_duplicate", "冰箱或清单已有同名食材，可能包含待核对批次。请核对后明确确认仍需购买。")
        ingredient, _ = Ingredient.objects.get_or_create(name=normalized["canonical_name"])
        item = ShoppingItem.objects.create(ingredient=ingredient, name=name,
            quantity_milli=normalized["quantity_milli"], unit=normalized["unit"])
        return 201, {"item": _item_dict(item), "existing_stock": existing,
                     "open_requests": pending, "needs_review_count": needs_review}

    return stock._execute(actor, request_id, "shop_add", normalized, work)


def _transition(actor, item_id, payload, *, kind, required_status, new_status):
    payload = stock._object(payload)
    stock._keys(payload, {"request_id", "version"})
    request_id = stock._request_id(payload.get("request_id"))
    item_id = stock._integer(item_id, "采购项编号", 1)
    version = stock._integer(payload.get("version"), "版本号")
    normalized = {"item_id": item_id, "version": version}

    def work(action):
        affected = ShoppingItem.objects.filter(pk=item_id, version=version, status__in=required_status).update(
            status=new_status, version=F("version") + 1, updated_at=timezone.now())
        if affected != 1:
            if not ShoppingItem.objects.filter(pk=item_id).exists():
                raise stock.InventoryError(404, "not_found", "采购项不存在。")
            raise stock.InventoryError(409, "version_conflict", "采购项已变化，请刷新后重试。")
        return 200, {"item": _item_dict(ShoppingItem.objects.get(pk=item_id))}

    return stock._execute(actor, request_id, kind, normalized, work)


def mark_bought(actor, item_id, payload):
    return _transition(actor, item_id, payload, kind="shop_bought", required_status=["needed"], new_status="bought")


def cancel_item(actor, item_id, payload):
    return _transition(actor, item_id, payload, kind="shop_cancel", required_status=["needed", "bought"], new_status="cancelled")


def receive_item(actor, item_id, payload):
    payload = stock._object(payload)
    stock._keys(payload, {"request_id", "version", "quantity", "location", "storage_status", "status", "package_date_status", "package_date", "purchase_date"})
    request_id = stock._request_id(payload.get("request_id"))
    item_id = stock._integer(item_id, "采购项编号", 1)
    version = stock._integer(payload.get("version"), "版本号")
    normalized = {
        "item_id": item_id, "version": version,
        "quantity_milli": stock.parse_amount(payload.get("quantity")),
        "location": stock._choice(payload.get("location"), stock.LOCATIONS, "位置"),
        "storage_status": stock._choice(payload.get("storage_status", "needs_check"), set(InventoryLot.StorageStatus.values), "储存状态"),
        "status": stock._choice(payload.get("status", "active"), {"active", "suspect"}, "食材状态"),
        "package_date_status": stock._choice(payload.get("package_date_status", "unknown"), set(InventoryLot.PackageDateStatus.values), "包装日期状态"),
        "package_date": stock._date(payload.get("package_date"), "包装日期"),
        "purchase_date": stock._date(payload.get("purchase_date"), "采购日期"),
    }
    stock._package_consistent(normalized)

    def work(action):
        item = ShoppingItem.objects.select_related("ingredient").filter(pk=item_id).first()
        if item is None:
            raise stock.InventoryError(404, "not_found", "采购项不存在。")
        if item.status != "bought" or item.version != version or item.received_lot_id or item.received_action_id:
            raise stock.InventoryError(409, "version_conflict", "采购项已变化或已入库，请刷新后重试。")
        lot = InventoryLot.objects.create(
            ingredient=item.ingredient, name=item.name, quantity_milli=normalized["quantity_milli"], unit=item.unit,
            location=normalized["location"], storage_status=normalized["storage_status"], status=normalized["status"],
            package_date_status=normalized["package_date_status"], package_date=normalized["package_date"],
            purchase_date=normalized["purchase_date"] or household_today()[0],
        )
        Movement.objects.create(lot=lot, action=action, delta_milli=lot.quantity_milli,
            unit=lot.unit, before_milli=0, after_milli=lot.quantity_milli)
        affected = ShoppingItem.objects.filter(pk=item_id, status="bought", version=version,
            received_lot__isnull=True, received_action__isnull=True).update(
                status="received", received_lot=lot, received_action=action,
                version=F("version") + 1, updated_at=timezone.now())
        if affected != 1:
            raise stock.InventoryError(409, "version_conflict", "采购项已入库或已变化。")
        return 201, {"item": _item_dict(ShoppingItem.objects.get(pk=item_id)), "lot": stock._lot_dict(lot)}

    return stock._execute(actor, request_id, "shop_receive", normalized, work)
