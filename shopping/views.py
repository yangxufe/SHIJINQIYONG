"""Server-rendered shopping flow and JSON adapters."""

from uuid import uuid4

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from inventory import services as stock
from inventory.api import BadJson, _body, _error
from shopping import services


def _page(request, *, error="", status=200, draft=None, retry=None):
    try:
        context = services.list_items(request.user)
    except stock.InventoryError as exc:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    add_draft = (draft or {}) if retry is None else {}
    context.update({"error": error, "draft": add_draft, "new_request_id":
                    add_draft.get("request_id") or str(uuid4()), "active_tab": "shopping", "response_status": status})
    for item in context["open"]:
        item["request_id"] = retry[1] if retry and retry[0] == item["id"] else str(uuid4())
        if retry and retry[0] == item["id"]:
            item["draft"] = draft or {}
    return render(request, "shopping/list.html", context, status=status)


@require_http_methods(["GET", "POST"])
def shopping_page(request):
    if request.method == "GET":
        return _page(request)
    payload = {key: request.POST.get(key) for key in ("request_id", "name", "quantity", "unit")}
    payload["confirm_duplicate"] = request.POST.get("confirm_duplicate") == "true"
    try:
        services.add_item(request.user, payload)
    except stock.InventoryError as exc:
        return _page(request, error=exc.message, status=exc.status, draft=request.POST.dict())
    messages.success(request, "已加入采购清单；买到后再标记，实际放入冰箱时才入库。")
    return redirect("shopping_page")


def _form_action(request, item_id, operation):
    payload = {"request_id": request.POST.get("request_id"), "version": request.POST.get("version")}
    if operation == "receive":
        payload.update({key: request.POST.get(key) for key in
                        ("quantity", "location", "storage_status", "status", "package_date_status", "package_date", "purchase_date")})
    try:
        {"bought": services.mark_bought, "cancel": services.cancel_item,
         "receive": services.receive_item}[operation](request.user, item_id, payload)
    except stock.InventoryError as exc:
        return _page(request, error=exc.message, status=exc.status, draft=request.POST.dict(),
                     retry=(item_id, request.POST.get("request_id")))
    messages.success(request, {"bought": "已标记买到，尚未加入冰箱库存。", "cancel": "采购项已取消。",
                               "receive": "实际数量已入库，并记入库存流水。"}[operation])
    return redirect("shopping_page")


@require_POST
def shopping_bought(request, item_id):
    return _form_action(request, item_id, "bought")


@require_POST
def shopping_cancel(request, item_id):
    return _form_action(request, item_id, "cancel")


@require_POST
def shopping_receive(request, item_id):
    return _form_action(request, item_id, "receive")


def _api_run(fn):
    try:
        result = fn()
    except (BadJson, stock.InventoryError) as exc:
        return _error(exc)
    return JsonResponse(result["body"], status=result["status"])


@require_http_methods(["GET", "POST"])
def shopping_api(request):
    if request.method == "POST":
        return _api_run(lambda: services.add_item(request.user, _body(request)))
    try:
        return JsonResponse(services.list_items(request.user))
    except stock.InventoryError as exc:
        return _error(exc)


@require_POST
def shopping_bought_api(request, item_id):
    return _api_run(lambda: services.mark_bought(request.user, item_id, _body(request)))


@require_POST
def shopping_cancel_api(request, item_id):
    return _api_run(lambda: services.cancel_item(request.user, item_id, _body(request)))


@require_POST
def shopping_receive_api(request, item_id):
    return _api_run(lambda: services.receive_item(request.user, item_id, _body(request)))
