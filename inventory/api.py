"""Thin JSON adapters around the inventory service."""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from inventory import recognition, services


class BadJson(Exception):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BadJson("请求包含重复字段。")
        result[key] = value
    return result


def _reject_constant(value):
    raise BadJson("JSON 中不能包含非有限数字。")


def _body(request):
    if request.content_type != "application/json":
        raise BadJson("请使用 application/json。")
    try:
        payload = json.loads(request.body.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadJson("JSON 格式错误。") from exc
    if not isinstance(payload, dict):
        raise BadJson("请求必须是 JSON 对象。")
    return payload


def _error(exc):
    if isinstance(exc, BadJson):
        return JsonResponse({"error": {"code": "malformed_json", "message": str(exc)}}, status=400)
    response = JsonResponse({"error": {"code": exc.code, "message": exc.message}}, status=exc.status)
    if exc.status == 503:
        response["Retry-After"] = "2"
    return response


def _run(fn):
    try:
        result = fn()
    except (BadJson, services.InventoryError) as exc:
        return _error(exc)
    return JsonResponse(result["body"], status=result["status"])


@require_http_methods(["GET", "POST"])
def inventory_collection(request):
    if request.method == "POST":
        return _run(lambda: services.create_lot(request.user, _body(request)))
    try:
        data = services.list_lots(request.user, request.GET.get("page", "1"), request.GET.get("per_page", "50"), request.GET.get("q", ""))
    except services.InventoryError as exc:
        return _error(exc)
    return JsonResponse(data)


@require_http_methods(["POST"])
def recognize_photo(request):
    try:
        payload = _body(request)
        if set(payload) != {"image"}:
            raise BadJson("照片请求只接受 image 字段。")
        result = recognition.recognise(payload["image"])
    except (BadJson, recognition.RecognitionError) as exc:
        return _error(exc)
    return JsonResponse(result)


@require_http_methods(["PATCH"])
def inventory_detail(request, lot_id):
    return _run(lambda: services.edit_lot(request.user, lot_id, _body(request)))


@require_http_methods(["POST"])
def actions_collection(request):
    return _run(lambda: services.apply_action(request.user, _body(request)))


@require_GET
def action_detail(request, action_id):
    try:
        result = services.get_action(request.user, action_id)
    except services.InventoryError as exc:
        return _error(exc)
    return JsonResponse({"original_status": result["status"], "result": result["body"]})


@require_GET
def action_by_request(request, request_id):
    try:
        result = services.get_action_by_request(request.user, str(request_id))
    except services.InventoryError as exc:
        return _error(exc)
    return JsonResponse({"original_status": result["status"], "result": result["body"]})


@require_GET
def movements_collection(request):
    try:
        data = services.list_movements(request.user, request.GET.get("page", "1"), request.GET.get("per_page", "50"))
    except services.InventoryError as exc:
        return _error(exc)
    return JsonResponse(data)
