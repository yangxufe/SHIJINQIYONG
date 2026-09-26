from uuid import uuid4

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from inventory import services


def _inventory_context(request, draft=None, error=None):
    page = services.list_lots(request.user, request.GET.get("page", "1"), query=request.GET.get("q", ""))
    for item in page["items"]:
        item["form_request_id"] = str(uuid4())
    return {"page": page, "search_query": page["query"], "draft": draft or {}, "error": error, "new_request_id": (draft or {}).get("request_id") or str(uuid4())}


@require_http_methods(["GET", "POST"])
def inventory_page(request):
    if request.method == "POST":
        payload = request.POST.dict()
        payload.pop("csrfmiddlewaretoken", None)
        try:
            services.create_lot(request.user, payload)
        except services.InventoryError as exc:
            response = render(request, "inventory/list.html", _inventory_context(request, payload, exc.message), status=exc.status)
            if exc.status == 503:
                response["Retry-After"] = "2"
            return response
        messages.success(request, "批次已保存，入库流水已记录。")
        return redirect("inventory_page")
    try:
        context = _inventory_context(request)
    except services.InventoryError as exc:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    return render(request, "inventory/list.html", context)


@require_http_methods(["POST"])
def action_form(request):
    original = request.POST.dict()
    try:
        payload = {
            "request_id": original.get("request_id"),
            "kind": original.get("kind"),
            "note": original.get("note", ""),
            "items": [{"lot_id": original.get("lot_id"), "version": original.get("version"), "quantity": original.get("quantity"), "unit": original.get("unit")}],
        }
        outcome = services.apply_action(request.user, payload)
    except services.InventoryError as exc:
        response = render(request, "inventory/error.html", {"error": exc.message, "retry": original if exc.status == 503 else None}, status=exc.status)
        if exc.status == 503:
            response["Retry-After"] = "2"
        return response
    messages.success(request, f"记录已保存，动作编号 {outcome['body']['action_id']}。")
    return redirect("inventory_page")


@require_http_methods(["GET", "POST"])
def edit_page(request, lot_id):
    try:
        if request.method == "POST":
            payload = request.POST.dict()
            payload.pop("csrfmiddlewaretoken", None)
            services.edit_lot(request.user, lot_id, payload)
            messages.success(request, "批次信息已更新。")
            return redirect("inventory_page")
        payload = services.get_lot(request.user, lot_id)
        payload["request_id"] = str(uuid4())
    except services.InventoryError as exc:
        if request.method == "GET":
            return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
        payload = request.POST.dict()
        response = render(request, "inventory/edit.html", {"lot_id": lot_id, "draft": payload, "error": exc.message}, status=exc.status)
        if exc.status == 503:
            response["Retry-After"] = "2"
        return response
    return render(request, "inventory/edit.html", {"lot_id": lot_id, "draft": payload})

# Create your views here.
