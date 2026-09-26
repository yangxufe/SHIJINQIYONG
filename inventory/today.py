"""Read-only, explainable ordering of current household lots."""

from django.db.models import F, Q

from inventory.availability import household_today, usable_lots
from inventory.models import InventoryLot
from inventory.services import _lot_dict, _require_member


def _review_reasons(lot, today):
    reasons = []
    if lot.status == InventoryLot.Status.SUSPECT:
        reasons.append("疑似变质，请核对并决定是否丢弃")
    if lot.storage_status == InventoryLot.StorageStatus.NEEDS_CHECK:
        reasons.append("储存状况待核对")
    if lot.package_date_status == InventoryLot.PackageDateStatus.KNOWN and lot.package_date < today:
        reasons.append("包装日期已过，不作为可用食材")
    return reasons


def get_today(actor):
    _require_member(actor)
    today, zone_name = household_today()
    stock = InventoryLot.objects.select_related("ingredient").filter(
        status__in=[InventoryLot.Status.ACTIVE, InventoryLot.Status.SUSPECT],
        quantity_milli__gt=0,
    )
    expired = Q(package_date_status=InventoryLot.PackageDateStatus.KNOWN, package_date__lt=today)
    needs_review = stock.filter(Q(status=InventoryLot.Status.SUSPECT) | Q(storage_status=InventoryLot.StorageStatus.NEEDS_CHECK) | expired)
    usable = usable_lots()

    arranged = []
    for lot in usable.order_by("-manual_priority", F("planned_use_date").asc(nulls_last=True), "created_at", "id")[:3]:
        item = _lot_dict(lot)
        item["reason"] = (
            "手动优先；" if lot.manual_priority else ""
        ) + (
            "计划已过" if lot.planned_use_date and lot.planned_use_date < today else
            "按计划日期安排" if lot.planned_use_date else "按入库时间安排"
        )
        arranged.append(item)

    review = []
    for lot in needs_review.order_by("created_at", "id")[:3]:
        item = _lot_dict(lot)
        item["reasons"] = _review_reasons(lot, today)
        review.append(item)

    return {
        "today": today.isoformat(),
        "time_zone": zone_name,
        "arrange": arranged,
        "needs_review": review,
        "arrange_count": usable.count(),
        "needs_review_count": needs_review.count(),
        "stock_count": stock.count(),
    }
