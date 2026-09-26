from urllib.parse import quote_plus
from uuid import UUID, uuid4

from django.contrib import messages
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from inventory import services as inventory_service
from meals import services
from meals.forms import FamilyRecipeForm
from meals.media import delete_upload, media_path, save_upload
from meals.models import FamilyRecipe, RecipeMedia


def _error_response(exc):
    response = JsonResponse({"error": {"code": exc.code, "message": exc.message}}, status=exc.status)
    if exc.status == 503:
        response["Retry-After"] = "2"
    return response


def _detail_context(recipe, request_id, draft):
    for row in recipe["ingredients"]:
        for lot in row["lots"]:
            lot["quantity_value"] = draft.get(f"quantity_{lot['id']}", "")
            lot["version_value"] = draft.get(f"version_{lot['id']}", lot["version"])
    context = {"recipe": recipe, "request_id": request_id, "draft": draft, "upload_request_id": str(uuid4())}
    if recipe["version"] is not None:
        context["media_items"] = RecipeMedia.objects.filter(recipe_id=UUID(recipe["id"].removeprefix("family-")))
    return context


@require_GET
def recipe_list(request):
    category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()
    find = request.GET.get("find", "").strip()
    if len(find) > 80:
        find = ""
    try:
        context = services.list_recipes(request.user, category=category, query=query)
    except inventory_service.InventoryError as exc:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    context["find"] = find
    if find:
        encoded = quote_plus(find + " 做法")
        context["search_links"] = {
            "video": "https://search.bilibili.com/all?keyword=" + encoded,
            "article": "https://www.bing.com/search?q=" + encoded,
            "images": "https://www.bing.com/images/search?q=" + encoded,
        }
    return render(request, "meals/list.html", context)


@require_GET
def recipe_list_api(request):
    try:
        result = services.list_recipes(request.user, category=request.GET.get("category", "").strip(), query=request.GET.get("q", "").strip())
    except inventory_service.InventoryError as exc:
        return _error_response(exc)
    return JsonResponse(result)


def _family_recipe(recipe_id):
    if not recipe_id.startswith("family-"):
        raise inventory_service.InventoryError(404, "not_found", "家庭菜谱不存在。")
    try:
        pk = UUID(recipe_id.removeprefix("family-"))
    except ValueError as exc:
        raise inventory_service.InventoryError(404, "not_found", "家庭菜谱不存在。") from exc
    recipe = FamilyRecipe.objects.filter(pk=pk).first()
    if recipe is None:
        raise inventory_service.InventoryError(404, "not_found", "家庭菜谱不存在。")
    return recipe


def _recipe_initial(recipe):
    return {
        "title": recipe.title, "ingredients_text": "\n".join(recipe.ingredients),
        "steps_text": "\n".join(recipe.steps), "category": recipe.category,
        "tags_text": "、".join(recipe.tags), "source_type": recipe.source_type,
        "source_url": recipe.source_url, "source_note": recipe.source_note,
        "request_id": str(uuid4()), "version": recipe.version,
    }


def _recipe_form_page(request, form, *, recipe=None, error="", status=200):
    return render(request, "meals/form.html", {
        "form": form, "recipe": recipe, "error": error,
        "page_title": "编辑家庭菜谱" if recipe else "新增家庭菜谱",
        "form_action": ("recipe_edit" if recipe else "recipe_new"),
        "recipe_id": f"family-{recipe.pk}" if recipe else "",
    }, status=status)


@require_http_methods(["GET", "POST"])
def recipe_new(request):
    if request.method == "GET":
        return _recipe_form_page(request, FamilyRecipeForm(initial={"request_id": str(uuid4()), "category": "家常菜", "source_type": "own"}))
    if any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        return _recipe_form_page(request, FamilyRecipeForm(request.POST), error="表单包含重复字段，请刷新后重试。", status=422)
    form = FamilyRecipeForm(request.POST)
    if not form.is_valid():
        return _recipe_form_page(request, form, status=422)
    try:
        recipe = services.save_family_recipe(request.user, form.cleaned_data)
    except inventory_service.InventoryError as exc:
        return _recipe_form_page(request, form, error=exc.message, status=exc.status)
    messages.success(request, "家庭菜谱已保存，家中成员登录后可以查看。")
    return redirect("recipe_detail", recipe_id=f"family-{recipe.pk}")


@require_http_methods(["GET", "POST"])
def recipe_edit(request, recipe_id):
    try:
        recipe = _family_recipe(recipe_id)
    except inventory_service.InventoryError as exc:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    if request.method == "GET":
        return _recipe_form_page(request, FamilyRecipeForm(initial=_recipe_initial(recipe)), recipe=recipe)
    if any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        return _recipe_form_page(request, FamilyRecipeForm(request.POST), recipe=recipe, error="表单包含重复字段，请刷新后重试。", status=422)
    form = FamilyRecipeForm(request.POST)
    if not form.is_valid():
        return _recipe_form_page(request, form, recipe=recipe, status=422)
    try:
        services.save_family_recipe(request.user, form.cleaned_data, existing=recipe)
    except inventory_service.InventoryError as exc:
        return _recipe_form_page(request, form, recipe=recipe, error=exc.message, status=exc.status)
    messages.success(request, "家庭菜谱已更新。")
    return redirect("recipe_detail", recipe_id=recipe_id)


@require_GET
def recipe_detail(request, recipe_id):
    try:
        recipe = services.get_recipe(request.user, recipe_id)
    except inventory_service.InventoryError as exc:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    return render(request, "meals/detail.html", _detail_context(recipe, str(uuid4()), {}))


@require_POST
def recipe_upload(request, recipe_id):
    try:
        recipe = _family_recipe(recipe_id)
        if any(len(request.POST.getlist(key)) != 1 for key in request.POST) or any(len(request.FILES.getlist(key)) != 1 for key in request.FILES):
            raise inventory_service.InventoryError(422, "invalid_input", "上传表单包含重复字段。")
        if not {"kind", "request_id"} <= set(request.POST) or not set(request.POST) <= {"csrfmiddlewaretoken", "kind", "caption", "request_id"} or set(request.FILES) != {"file"}:
            raise inventory_service.InventoryError(422, "invalid_input", "上传表单字段无效。")
        save_upload(request.user, recipe, request.FILES.get("file"), kind=request.POST.get("kind"),
                    caption=request.POST.get("caption"), request_id=request.POST.get("request_id"))
    except inventory_service.InventoryError as exc:
        try:
            detail = services.get_recipe(request.user, recipe_id)
        except inventory_service.InventoryError:
            return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
        context = _detail_context(detail, str(uuid4()), {})
        context["upload_error"] = exc.message
        context["upload_request_id"] = request.POST.get("request_id") or str(uuid4())
        response = render(request, "meals/detail.html", context, status=exc.status)
        if exc.status == 503:
            response["Retry-After"] = "2"
        return response
    messages.success(request, "文件已保存，仅登录的家庭成员可以查看。")
    return redirect("recipe_detail", recipe_id=recipe_id)


def _media_item(recipe_id, media_id):
    recipe = _family_recipe(recipe_id)
    try:
        pk = UUID(str(media_id))
    except ValueError as exc:
        raise inventory_service.InventoryError(404, "not_found", "附件不存在。") from exc
    item = RecipeMedia.objects.filter(pk=pk, recipe=recipe).first()
    if item is None:
        raise inventory_service.InventoryError(404, "not_found", "附件不存在。")
    return recipe, item


def _file_chunks(path, start, length):
    with path.open("rb") as source:
        source.seek(start)
        remaining = length
        while remaining:
            chunk = source.read(min(65_536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _byte_range(value, total):
    if not value:
        return 0, total - 1, False
    if not value.startswith("bytes=") or "," in value:
        raise ValueError("Invalid range")
    part = value[6:]
    if "-" not in part:
        raise ValueError("Invalid range")
    left, right = part.split("-", 1)
    if not left and right.isdecimal():
        count = int(right)
        if count == 0:
            raise ValueError("Invalid range")
        return max(0, total - count), total - 1, True
    if not left.isdecimal() or (right and not right.isdecimal()):
        raise ValueError("Invalid range")
    start = int(left)
    end = min(int(right), total - 1) if right else total - 1
    if start >= total or end < start:
        raise ValueError("Invalid range")
    return start, end, True


@require_http_methods(["GET", "HEAD"])
def recipe_media_file(request, recipe_id, media_id):
    try:
        _, item = _media_item(recipe_id, media_id)
    except inventory_service.InventoryError:
        return HttpResponse(status=404)
    path = media_path(item)
    if not path.is_file():
        return HttpResponse(status=404)
    total = path.stat().st_size
    if not total:
        return HttpResponse(status=404)
    try:
        start, end, partial = _byte_range(request.headers.get("Range"), total)
    except ValueError:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{total}"
        return response
    size = end - start + 1
    if request.method == "HEAD":
        response = HttpResponse(status=206 if partial else 200, content_type=item.mime_type)
    else:
        response = StreamingHttpResponse(_file_chunks(path, start, size), status=206 if partial else 200, content_type=item.mime_type)
    response["Content-Length"] = str(size)
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = "inline"
    if partial:
        response["Content-Range"] = f"bytes {start}-{end}/{total}"
    return response


@require_POST
def recipe_media_delete(request, recipe_id, media_id):
    try:
        recipe, item = _media_item(recipe_id, media_id)
        delete_upload(request.user, recipe, item)
    except inventory_service.InventoryError as exc:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    messages.success(request, "附件已删除。")
    return redirect("recipe_detail", recipe_id=recipe_id)


@require_POST
def recipe_cook(request, recipe_id):
    if any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        exc = inventory_service.InventoryError(422, "invalid_input", "表单包含重复字段，请刷新后重试。")
    else:
        payload = request.POST.dict()
        payload.pop("csrfmiddlewaretoken", None)
        try:
            services.cook_recipe(request.user, recipe_id, payload)
        except inventory_service.InventoryError as caught:
            exc = caught
        else:
            messages.success(request, "已记录本次实际用量，并按批次扣减库存与写入流水。")
            return redirect("recipe_detail", recipe_id=recipe_id)
    try:
        recipe = services.get_recipe(request.user, recipe_id)
    except inventory_service.InventoryError:
        return render(request, "inventory/error.html", {"error": exc.message}, status=exc.status)
    context = _detail_context(recipe, request.POST.get("request_id") or str(uuid4()), request.POST)
    context["error"] = exc.message
    response = render(request, "meals/detail.html", context, status=exc.status)
    if exc.status == 503:
        response["Retry-After"] = "2"
    return response
