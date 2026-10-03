"""Mobile-first recipe workbench, explicit confirmation, and private settings."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from uuid import UUID, uuid4, uuid5

from django.contrib import messages
from django.db import OperationalError, transaction
from django.db.models import F
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.security import has_role
from inventory import services as stock
from meals.models import FamilyRecipe, HouseholdTaste, MenuPlan, MenuShoppingContribution, RecipeFeedback, RecipeRequest, TasteProfile
from meals.models import GenerationTask
from inventory.models import BusinessAction
from shopping import services as shopping
from meals.generation import GenerationUnavailable, cancel_task, provider_configuration, queue_generation
from meals.workbench import calculate_actual_nutrition, effective_taste, evaluate_menu, inventory_signature, ranked_candidates, specs_for_actor
from meals.workbench_forms import RecipeConditionsForm, TasteProfileForm


def _error(request, message, status=422):
    return render(request, "inventory/error.html", {"error": message}, status=status)


def _json_digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _provider_kind():
    try:
        return provider_configuration()[0]
    except GenerationUnavailable:
        return ""


@require_http_methods(["GET", "POST"])
def workbench_page(request):
    if request.method == "GET":
        text = request.GET.get("raw_text", "")[:600]
        form = RecipeConditionsForm(initial={"request_id": uuid4(), "people": 2, "max_minutes": 30,
                                              "spice_max": 1, "raw_text": text})
        direct = request.GET.get("direct") == "1"
        provider = _provider_kind() if direct else ""
        return render(request, "meals/workbench.html", {"form": form, "confirmed": False,
                      "direct": direct, "configured_provider": provider})
    if any(len(request.POST.getlist(key)) != 1 for key in request.POST if key not in {"goals", "equipment"}):
        return _error(request, "条件表单包含重复字段。")
    form = RecipeConditionsForm(request.POST)
    if not form.is_valid():
        return render(request, "meals/workbench.html", {"form": form, "confirmed": False}, status=422)
    initial, parsed = RecipeConditionsForm.interpreted_initial(form.cleaned_data)
    form = RecipeConditionsForm(initial=initial)
    return render(request, "meals/workbench.html", {"form": form, "confirmed": True, "parsed": parsed})


@require_POST
def confirm_conditions(request):
    if any(len(request.POST.getlist(key)) != 1 for key in request.POST if key not in {"goals", "equipment"}):
        return _error(request, "条件表单包含重复字段。")
    form = RecipeConditionsForm(request.POST)
    if not form.is_valid():
        return render(request, "meals/workbench.html", {"form": form, "confirmed": True,
                      "direct": request.POST.get("generate") == "yes",
                      "configured_provider": _provider_kind()}, status=422)
    conditions = form.cleaned_data["conditions"]
    request_id = form.cleaned_data["request_id"]
    digest = _json_digest(conditions)
    _, _, preference_version = effective_taste(request.user, conditions)
    try:
        with transaction.atomic():
            original = RecipeRequest.objects.filter(owner=request.user, request_id=request_id).first()
            if original:
                if original.digest != digest:
                    return _error(request, "此请求编号已用于不同条件，请刷新页面后重试。", 409)
                plan = original
            else:
                plan = RecipeRequest.objects.create(owner=request.user, request_id=request_id, digest=digest,
                    raw_text=conditions["raw_text"], conditions=conditions,
                    inventory_signature=inventory_signature(), preference_version=preference_version)
    except OperationalError as exc:
        if stock._is_busy(exc):
            return _error(request, "数据库暂时繁忙，请用原页面重试。", 503)
        raise
    if request.POST.get("generate") == "yes":
        try:
            task = queue_generation(request.user, plan, str(uuid5(plan.request_id, "direct-generation")),
                                    external_consent=request.POST.get("external_consent") == "on")
        except GenerationUnavailable as exc:
            messages.warning(request, "生成服务未配置或暂不可用，已改为本地菜谱匹配。错误代码：" + exc.code)
        except stock.InventoryError as exc:
            return _error(request, exc.message, exc.status)
        else:
            return redirect("generation_detail", task_id=task.pk)
    return redirect("workbench_results", plan_id=plan.pk)


def _owned_request(request, plan_id):
    plan = RecipeRequest.objects.filter(pk=plan_id, owner=request.user).first()
    if plan is None:
        raise Http404
    return plan


@require_GET
def workbench_results(request, plan_id):
    plan = _owned_request(request, plan_id)
    conditions = plan.conditions
    candidates = ranked_candidates(request.user, conditions)
    all_specs = specs_for_actor(request.user)
    unquantified = [{"id": f"family-{recipe.pk}", "title": recipe.title} for recipe in
                    FamilyRecipe.objects.filter(review_state="needs_review")[:20]]
    try:
        configured_provider = provider_configuration()[0]
    except GenerationUnavailable:
        configured_provider = ""
    shared_ids = set(TasteProfile.objects.filter(user_id__in=conditions["participants"],
                                                     share_restrictions=True).values_list("user_id", flat=True))
    return render(request, "meals/results.html", {"plan": plan, "conditions": conditions,
        "candidates": candidates, "unquantified": unquantified, "total_structured": len(all_specs),
        "menu_request_id": uuid4(), "generation_request_id": uuid4(),
        "inventory_changed": plan.inventory_signature != inventory_signature(), "configured_provider": configured_provider,
        "participants_need_manual_check": any(member_id not in shared_ids for member_id in conditions["participants"])})


@require_POST
def generation_submit(request, plan_id):
    plan = _owned_request(request, plan_id)
    if set(request.POST) - {"csrfmiddlewaretoken", "request_id", "external_consent"}:
        return _error(request, "生成表单字段无效。")
    try:
        task = queue_generation(request.user, plan, request.POST.get("request_id"),
                                external_consent=request.POST.get("external_consent") == "on")
    except GenerationUnavailable as exc:
        return _error(request, "模型尚未配置或不可用；本地菜谱仍可使用。错误代码：" + exc.code, 503)
    except stock.InventoryError as exc:
        return _error(request, exc.message, exc.status)
    return redirect("generation_detail", task_id=task.pk)


def _owned_generation(request, task_id):
    task = GenerationTask.objects.select_related("recipe_request").filter(pk=task_id, owner=request.user).first()
    if task is None:
        raise Http404
    return task


@require_GET
def generation_detail(request, task_id):
    task = _owned_generation(request, task_id)
    match = None
    safety_notes = []
    if task.status == "success" and task.result:
        from meals.safety_rules import notes
        match = evaluate_menu([task.result], servings=task.recipe_request.conditions["people"],
                              conditions=task.recipe_request.conditions, actor=request.user)
        safety_notes = notes(task.result["safety_rule_ids"])
    return render(request, "meals/generation.html", {"task": task, "match": match, "safety_notes": safety_notes})


@require_GET
def generation_status(request, task_id):
    task = _owned_generation(request, task_id)
    return JsonResponse({"id": str(task.pk), "status": task.status, "error_code": task.error_code,
                         "result_available": task.status == "success"})


@require_POST
def generation_cancel(request, task_id):
    _owned_generation(request, task_id)
    cancel_task(request.user, task_id)
    return redirect("generation_detail", task_id=task_id)


@require_POST
def generation_save(request, task_id):
    task = _owned_generation(request, task_id)
    if task.status != "success" or not task.result:
        return _error(request, "只有通过服务端校验的完成任务才能保存。", 409)
    try:
        save_id = UUID(request.POST.get("request_id", ""))
    except ValueError:
        return _error(request, "保存请求编号无效。")
    if save_id != task.request_id:
        return _error(request, "保存请求编号必须与生成任务一致。", 409)
    from meals.structured import validate_spec
    try:
        spec = validate_spec(task.result)
    except ValueError:
        return _error(request, "生成结果已无法通过校验，不能保存。", 409)
    digest = _json_digest(spec)
    with transaction.atomic():
        existing = FamilyRecipe.objects.filter(created_by=request.user, create_request_id=save_id).first()
        if existing:
            if existing.create_digest != digest:
                return _error(request, "保存编号已用于其他菜谱。", 409)
            recipe = existing
        else:
            recipe = FamilyRecipe.objects.create(title=spec["title"], ingredients=[row["name"] for row in spec["ingredients"]],
                steps=[row["action"] for row in spec["steps"]], category=spec["category"], tags=[], source_type="own",
                source_note="AI 生成并通过已知规则校验；未经实测。", created_by=request.user,
                create_request_id=save_id, create_digest=digest, structured_data=spec, review_state="machine_checked")
    return redirect("recipe_detail", recipe_id=f"family-{recipe.pk}")


@require_POST
def create_menu(request, plan_id):
    plan = _owned_request(request, plan_id)
    submitted = request.POST.getlist("recipe_id")
    if not 1 <= len(submitted) <= 4 or len(set(submitted)) != len(submitted):
        return _error(request, "请选择1至4道不同菜谱。")
    try:
        menu_id = UUID(request.POST.get("request_id", ""))
    except ValueError:
        return _error(request, "菜单请求编号无效。")
    specs = specs_for_actor(request.user)
    if any(recipe_id not in specs for recipe_id in submitted):
        return _error(request, "菜谱已变化，请刷新后重试。", 409)
    if plan.conditions["meal_type"] == "single" and len(submitted) != 1:
        return _error(request, "本次选择了单道菜模式。")
    existing = MenuPlan.objects.filter(pk=menu_id).first()
    if existing:
        if existing.owner_id != request.user.pk or existing.recipe_request_id != plan.pk or existing.recipe_ids != submitted:
            return _error(request, "菜单编号已用于其他选择。", 409)
        return redirect("menu_detail", menu_id=menu_id)
    try:
        with transaction.atomic():
            menu = MenuPlan.objects.create(id=menu_id, owner=request.user, recipe_request=plan, recipe_ids=submitted)
    except OperationalError as exc:
        if stock._is_busy(exc):
            return _error(request, "数据库暂时繁忙，请用原编号重试。", 503)
        raise
    return redirect("menu_detail", menu_id=menu.pk)


def _owned_menu(request, menu_id):
    menu = MenuPlan.objects.select_related("recipe_request").filter(pk=menu_id, owner=request.user).first()
    if menu is None:
        raise Http404
    return menu


@require_GET
def menu_detail(request, menu_id):
    menu = _owned_menu(request, menu_id)
    specs = specs_for_actor(request.user)
    if any(recipe_id not in specs for recipe_id in menu.recipe_ids):
        return _error(request, "菜谱内容已变化，请重新选择菜单。", 409)
    selected = [specs[key] for key in menu.recipe_ids]
    result = evaluate_menu(selected, servings=menu.recipe_request.conditions["people"],
                           conditions=menu.recipe_request.conditions, actor=request.user)
    needs_check = _participants_need_check(menu.recipe_request.conditions)
    schedule = []
    minute = 0
    for spec in selected:
        schedule.append({"title": spec["title"], "start": minute, "end": minute + spec["total_minutes"],
                         "equipment": "、".join(spec["equipment"])})
        minute += spec["total_minutes"]
    return render(request, "meals/menu.html", {"menu": menu, "selected": selected, "result": result,
        "conditions": menu.recipe_request.conditions, "request_id": uuid4(), "shopping_request_id": uuid4(),
        "snapshot": _json_digest({"specs": selected, "result": result, "menu_version": menu.version}),
        "purchase_gaps": _purchase_gaps(result), "cook_lots": _cook_lots(result),
        "existing_contributions": set(menu.shopping_contributions.filter(menu_version=menu.version).values_list("ingredient_name", flat=True)),
        "participants_need_manual_check": needs_check, "schedule": schedule, "sequential_minutes": minute})


def _participants_need_check(conditions):
    shared_ids = set(TasteProfile.objects.filter(user_id__in=conditions["participants"],
                                                     share_restrictions=True).values_list("user_id", flat=True))
    return any(member_id not in shared_ids for member_id in conditions["participants"])


def _menu_evaluation(actor, menu):
    specs = specs_for_actor(actor)
    if any(recipe_id not in specs for recipe_id in menu.recipe_ids):
        raise stock.InventoryError(409, "recipe_changed", "菜谱内容已变化，请重新选择菜单。")
    selected = [specs[key] for key in menu.recipe_ids]
    result = evaluate_menu(selected, servings=menu.recipe_request.conditions["people"],
                           conditions=menu.recipe_request.conditions, actor=actor)
    return selected, result, _json_digest({"specs": selected, "result": result, "menu_version": menu.version})


def _purchase_gaps(result):
    grouped = defaultdict(int)
    for gap in result["gaps"]:
        grouped[(gap["ingredient"], gap["unit"])] += stock.parse_amount(gap["quantity"])
    return [{"name": name, "unit": unit, "quantity": stock.format_amount(amount), "key": f"{name}|{unit}"}
            for (name, unit), amount in sorted(grouped.items())]


def _cook_lots(result):
    grouped = {}
    for allocation in result["allocations"]:
        lot_id = allocation["lot_id"]
        if lot_id not in grouped:
            grouped[lot_id] = {"lot_id": lot_id, "version": allocation["lot_version"],
                               "unit": allocation["unit"], "quantity_milli": 0, "names": set()}
        grouped[lot_id]["quantity_milli"] += stock.parse_amount(allocation["quantity"])
        grouped[lot_id]["names"].add(allocation["ingredient"])
    return [{**row, "quantity": stock.format_amount(row["quantity_milli"]), "names": "、".join(sorted(row["names"]))}
            for row in grouped.values()]


@require_POST
def menu_add_shopping(request, menu_id):
    menu = _owned_menu(request, menu_id)
    try:
        requested = request.POST.getlist("gap")
        confirm_duplicate = request.POST.get("confirm_duplicate") == "on"
        with transaction.atomic():
            menu.refresh_from_db()
            if menu.executed_action_id:
                return _error(request, "本餐已经记录实际使用，不能再加入缺料。", 409)
            _, result, snapshot = _menu_evaluation(request.user, menu)
            if request.POST.get("snapshot") != snapshot or not result["feasible"]:
                return _error(request, "菜单或库存已变化，请刷新后重新确认采购差额。", 409)
            gaps = {gap["key"]: gap for gap in _purchase_gaps(result)}
            if not requested or len(requested) != len(set(requested)) or any(key not in gaps for key in requested):
                return _error(request, "请选择当前菜单的有效缺料。")
            for key in requested:
                gap = gaps[key]
                existing = MenuShoppingContribution.objects.filter(menu=menu, menu_version=menu.version,
                    ingredient_name=gap["name"], unit=gap["unit"]).first()
                if existing:
                    continue
                purchase_field = f"buy_{key}"
                submitted_amounts = request.POST.getlist(purchase_field)
                if len(submitted_amounts) > 1:
                    return _error(request, "采购数量字段重复，请刷新后重试。")
                purchase_quantity = stock.format_amount(stock.parse_amount(
                    submitted_amounts[0] if submitted_amounts else gap["quantity"]))
                stable_id = uuid5(menu.id, f"shopping:{menu.version}:{key}")
                outcome = shopping.add_item(request.user, {"request_id": str(stable_id), "name": gap["name"],
                    "quantity": purchase_quantity, "unit": gap["unit"], "confirm_duplicate": confirm_duplicate})
                MenuShoppingContribution.objects.create(menu=menu, menu_version=menu.version,
                    ingredient_name=gap["name"], unit=gap["unit"], shopping_item_id=outcome["body"]["item"]["id"])
    except stock.InventoryError as exc:
        return _error(request, exc.message, exc.status)
    messages.success(request, "所选净缺口已加入采购清单；买到后仍须单独确认入库。")
    return redirect("menu_detail", menu_id=menu.id)


@require_POST
def menu_cook(request, menu_id):
    menu = _owned_menu(request, menu_id)
    try:
        action_id = UUID(request.POST.get("request_id", ""))
    except ValueError:
        return _error(request, "实际使用请求编号无效。")
    original = BusinessAction.objects.filter(actor=request.user, request_id=action_id).first()
    if original:
        if original.kind == "cook" and menu.executed_action_id == original.pk:
            messages.success(request, f"这次使用已记录，流水动作 #{original.pk}。")
            return redirect("menu_detail", menu_id=menu.id)
        return _error(request, "该请求编号已用于其他库存操作。", 409)
    try:
        with transaction.atomic():
            menu.refresh_from_db()
            if menu.executed_action_id:
                return _error(request, "本餐已记录实际使用，请建立新的用餐计划。", 409)
            selected, result, snapshot = _menu_evaluation(request.user, menu)
            if request.POST.get("snapshot") != snapshot or not result["feasible"] or result["gaps"]:
                return _error(request, "菜单缺料或库存已变化，请刷新后重新核对实际用量。", 409)
            lots = _cook_lots(result)
            if not lots or len(lots) > 20:
                return _error(request, "本餐可扣减批次数量无效。", 409)
            expected_keys = {"csrfmiddlewaretoken", "request_id", "snapshot", "confirm_use"} | {f"actual_{row['lot_id']}" for row in lots}
            if _participants_need_check(menu.recipe_request.conditions):
                expected_keys.add("confirm_restrictions")
                if request.POST.get("confirm_restrictions") != "on":
                    return _error(request, "请先向未共享限制的同餐成员人工核对过敏与禁食要求。", 409)
            if set(request.POST) - {"csrfmiddlewaretoken"} != expected_keys - {"csrfmiddlewaretoken"} or request.POST.get("confirm_use") != "on":
                return _error(request, "请逐批核对并确认实际用量。")
            items = [{"lot_id": row["lot_id"], "version": row["version"], "quantity": request.POST[f"actual_{row['lot_id']}"],
                      "unit": row["unit"]} for row in lots]
            outcome = stock.apply_action(request.user, {"request_id": str(action_id), "kind": "cook",
                "items": items, "note": f"菜单 {menu.id} 实际使用"})
            actual_uses = outcome["body"]["items"]
            actual_nutrition = calculate_actual_nutrition(selected, actual_uses,
                                                            menu.recipe_request.conditions["people"])
            changed = MenuPlan.objects.filter(pk=menu.pk, executed_action__isnull=True, version=menu.version).update(
                executed_action_id=outcome["body"]["action_id"], actual_uses=actual_uses,
                actual_nutrition=actual_nutrition, updated_at=timezone.now())
            if changed != 1:
                raise stock.InventoryError(409, "menu_changed", "菜单已经变化，请刷新。")
    except stock.InventoryError as exc:
        return _error(request, exc.message, exc.status)
    messages.success(request, f"已按实际用量扣减库存并记录流水动作 #{outcome['body']['action_id']}。若实际量不同，先前营养估算不再适用。")
    return redirect("menu_detail", menu_id=menu.id)


@require_POST
def recipe_feedback(request, plan_id, recipe_id):
    plan = _owned_request(request, plan_id)
    if recipe_id not in specs_for_actor(request.user):
        raise Http404
    verdict = request.POST.get("verdict", "")
    if verdict not in {"like", "dislike", "too_spicy", "too_sweet", "too_complex", "make_again", "clear"}:
        return _error(request, "反馈选项无效。")
    with transaction.atomic():
        if verdict == "clear":
            RecipeFeedback.objects.filter(user=request.user, recipe_key=recipe_id).delete()
        else:
            RecipeFeedback.objects.update_or_create(user=request.user, recipe_key=recipe_id, defaults={"verdict": verdict})
    return redirect("workbench_results", plan_id=plan.pk)


def _profile_initial(profile):
    data = profile.data if profile else {}
    initial = {key: "、".join(data.get(key, [])) for key in
               ("liked_cuisines", "disliked_cuisines", "liked_ingredients", "disliked_ingredients", "allergens", "forbidden", "tried_cuisines", "made_methods", "liked_methods", "available_equipment", "disliked_tastes", "liked_tastes", "explore_cuisines")}
    initial.update(version=profile.version if profile else 0, spice_max=data.get("spice_max", 1),
                   willing_to_explore=data.get("willing_to_explore", False),
                   share_restrictions=profile.share_restrictions if isinstance(profile, TasteProfile) else False)
    return initial


@require_http_methods(["GET", "POST"])
def taste_profile(request, scope="personal"):
    household = scope == "household"
    if household and not has_role(request.user, "admin"):
        return _error(request, "仅家庭管理员可编辑家庭口味。", 403)
    profile = HouseholdTaste.objects.filter(pk=1).first() if household else TasteProfile.objects.filter(user=request.user).first()
    if request.method == "GET":
        return render(request, "meals/taste.html", {"form": TasteProfileForm(initial=_profile_initial(profile)), "household": household})
    if any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        return _error(request, "口味表单包含重复字段。")
    form = TasteProfileForm(request.POST)
    if not form.is_valid():
        return render(request, "meals/taste.html", {"form": form, "household": household}, status=422)
    version = form.cleaned_data["version"]
    data = form.cleaned_data["profile_data"]
    try:
        with transaction.atomic():
            if profile is None:
                if version != 0:
                    return _error(request, "配置已变化，请刷新。", 409)
                if household:
                    HouseholdTaste.objects.create(pk=1, data=data, version=1)
                else:
                    TasteProfile.objects.create(user=request.user, data=data, version=1,
                                                share_restrictions=form.cleaned_data["share_restrictions"])
            elif household:
                changed = HouseholdTaste.objects.filter(pk=1, version=version).update(data=data, version=F("version") + 1, updated_at=timezone.now())
                if not changed:
                    return _error(request, "配置已变化，请刷新。", 409)
            else:
                changed = TasteProfile.objects.filter(user=request.user, version=version).update(data=data,
                    share_restrictions=form.cleaned_data["share_restrictions"], version=F("version") + 1,
                    updated_at=timezone.now())
                if not changed:
                    return _error(request, "配置已变化，请刷新。", 409)
    except OperationalError as exc:
        if stock._is_busy(exc):
            return _error(request, "数据库暂时繁忙，请刷新后重试。", 503)
        raise
    messages.success(request, "口味配置已保存。")
    return redirect("household_taste" if household else "personal_taste")
