"""Match trusted lots for both built-in and household-authored recipes."""

import hashlib
import json
import re

from django.db import OperationalError, transaction
from django.utils import timezone

from inventory import services as inventory_service
from inventory.availability import usable_lots
from inventory.models import BusinessAction, InventoryLot
from meals.catalog import load_catalog
from meals.models import FamilyRecipe
from meals.structured import load_structured_catalog, validate_spec


SOURCE_LABELS = {"own": "家庭自写", "video": "视频教程", "article": "文字教程", "images": "图片教程"}
BROWSE_CATEGORIES = ("荤菜", "素菜", "汤羹", "其他")
BUILT_IN_CATEGORIES = {
    "tomato-egg": "素菜", "pepper-potato": "素菜", "cucumber-egg": "素菜",
    "broccoli": "素菜", "lettuce": "素菜", "seaweed-egg-soup": "汤羹",
    "tofu-potato-mild": "素菜", "cantonese-steamed-tofu": "素菜",
}


def _browse_category(recipe):
    if recipe["category"] in BROWSE_CATEGORIES:
        return recipe["category"]
    if not recipe["is_family"] and recipe["id"] in BUILT_IN_CATEGORIES:
        return BUILT_IN_CATEGORIES[recipe["id"]]
    return {"清淡素菜": "素菜"}.get(recipe["category"], "其他")


def _recipe_specs():
    built_in, canonical_by_name = load_catalog()
    recipes = [{**recipe, "source_type": "built_in", "source_label": "内置菜谱", "source_url": "",
                "source_note": "", "version": None, "is_family": False} for recipe in built_in]
    known_ids = {recipe["id"] for recipe in recipes}
    for spec in load_structured_catalog().values():
        if spec["id"] not in known_ids:
            recipes.append({"id": spec["id"], "name": spec["title"], "category": spec["category"], "tags": [],
                            "ingredients": [item["name"] for item in spec["ingredients"]],
                            "steps": [item["action"] for item in spec["steps"]], "source_type": "built_in",
                            "source_label": spec["source_label"], "source_url": "", "source_note": "",
                            "version": None, "is_family": False})
    for recipe in FamilyRecipe.objects.select_related("created_by").all():
        recipes.append({
            "id": f"family-{recipe.pk}", "name": recipe.title,
            "ingredients": recipe.ingredients, "steps": recipe.steps,
            "category": recipe.category, "tags": recipe.tags,
            "source_type": recipe.source_type, "source_label": SOURCE_LABELS.get(recipe.source_type, "家庭菜谱"),
            "source_url": recipe.source_url, "source_note": recipe.source_note,
            "version": recipe.version, "created_by": recipe.created_by.username, "is_family": True,
        })
    return recipes, canonical_by_name


def _catalog_matches(actor):
    inventory_service._require_member(actor)
    recipes, canonical_by_name = _recipe_specs()
    by_canonical = {}
    for lot in usable_lots().order_by("created_at", "id"):
        canonical = canonical_by_name.get(lot.ingredient.name, lot.ingredient.name)
        item = inventory_service._lot_dict(lot)
        by_canonical.setdefault(canonical, []).append(item)
    return recipes, by_canonical, canonical_by_name


def list_recipes(actor, *, category="", query="", matched_only=False):
    if len(category) > 20 or len(query) > 80:
        raise inventory_service.InventoryError(422, "invalid_input", "筛选条件过长。")
    recipes, by_canonical, _ = _catalog_matches(actor)
    categories = list(BROWSE_CATEGORIES)
    output = []
    for position, recipe in enumerate(recipes):
        browse_category = _browse_category(recipe)
        # Preserve old custom-category URLs while showing the four new groups.
        filter_category = browse_category if category in BROWSE_CATEGORIES else recipe["category"]
        if category and filter_category != category:
            continue
        if query and not any(query.casefold() in value.casefold() for value in [recipe["name"], *recipe["tags"], *recipe["ingredients"]]):
            continue
        missing = [name for name in recipe["ingredients"] if not by_canonical.get(name)]
        if matched_only and len(missing) == len(recipe["ingredients"]):
            continue
        output.append({
            "id": recipe["id"], "name": recipe["name"],
            "ingredients": recipe["ingredients"], "missing": missing,
            "matched_count": len(recipe["ingredients"]) - len(missing),
            "ingredient_count": len(recipe["ingredients"]),
            "has_all": not missing, "category": recipe["category"], "category_group": browse_category,
            "tags": recipe["tags"], "source_label": recipe["source_label"], "_position": position,
        })
    output.sort(key=lambda item: (-item["matched_count"] / item["ingredient_count"], -item["matched_count"], item["_position"]))
    for item in output:
        del item["_position"]
    return {"recipes": output, "count": len(output), "categories": categories,
            "active_category": category, "query": query}


def get_recipe(actor, recipe_id):
    recipes, by_canonical, _ = _catalog_matches(actor)
    recipe = next((item for item in recipes if item["id"] == recipe_id), None)
    if recipe is None:
        raise inventory_service.InventoryError(404, "not_found", "菜谱不存在。")
    ingredients = [{"name": name, "lots": by_canonical.get(name, [])} for name in recipe["ingredients"]]
    structured = load_structured_catalog().get(recipe_id)
    if recipe["is_family"]:
        family = FamilyRecipe.objects.filter(pk=recipe_id.removeprefix("family-")).first()
        if family and family.review_state in {"reviewed", "machine_checked"} and family.structured_data:
            try:
                structured = validate_spec(family.structured_data)
            except ValueError:
                structured = None
    from meals.safety_rules import notes
    return {**recipe, "ingredients": ingredients, "has_all": all(row["lots"] for row in ingredients),
            "structured": structured, "safety_notes": notes(structured["safety_rule_ids"]) if structured else []}


def cook_recipe(actor, recipe_id, payload):
    inventory_service._require_member(actor)
    recipes, canonical_by_name = _recipe_specs()
    recipe = next((item for item in recipes if item["id"] == recipe_id), None)
    if recipe is None:
        raise inventory_service.InventoryError(404, "not_found", "菜谱不存在。")
    if not isinstance(payload, dict):
        raise inventory_service.InventoryError(422, "invalid_input", "菜谱表单无效。")
    keys = set(payload) - {"request_id", "recipe_version"}
    if any(not re.fullmatch(r"(?:quantity|version)_[1-9][0-9]{0,9}", key) for key in keys):
        raise inventory_service.InventoryError(422, "invalid_input", "菜谱表单包含不支持的字段。")
    chosen_ids = {int(key[9:]) for key in keys if key.startswith("quantity_") and payload[key]}
    if not 1 <= len(chosen_ids) <= 20:
        raise inventory_service.InventoryError(422, "invalid_input", "请填写 1 至 20 个批次的实际用量。")
    lots = {lot.pk: lot for lot in InventoryLot.objects.select_related("ingredient").filter(pk__in=chosen_ids)}
    if set(lots) != chosen_ids:
        raise inventory_service.InventoryError(409, "version_conflict", "批次已变化，请刷新后重试。")
    items = []
    covered = set()
    for lot_id in sorted(chosen_ids):
        lot = lots[lot_id]
        canonical = canonical_by_name.get(lot.ingredient.name, lot.ingredient.name)
        covered.add(canonical)
        quantity = payload[f"quantity_{lot_id}"]
        if not isinstance(quantity, str):
            raise inventory_service.InventoryError(422, "invalid_input", "数量必须是文本。")
        items.append({"lot_id": lot_id, "version": payload.get(f"version_{lot_id}"), "quantity": quantity.strip(), "unit": lot.unit})
    note = f"家庭菜谱：{recipe_id}" if recipe_id.startswith("family-") else f"菜谱：{recipe['name']}"
    action_payload = {"request_id": payload.get("request_id"), "kind": "cook", "items": items, "note": note}
    request_id = inventory_service._request_id(payload.get("request_id"))
    if BusinessAction.objects.filter(actor=actor, request_id=request_id).exists():
        return inventory_service.apply_action(actor, action_payload)
    if any(canonical_by_name.get(lot.ingredient.name, lot.ingredient.name) not in recipe["ingredients"] for lot in lots.values()):
        raise inventory_service.InventoryError(422, "invalid_input", "所选批次不是这道菜的食材。")
    if recipe["version"] is None:
        if payload.get("recipe_version") not in (None, ""):
            raise inventory_service.InventoryError(422, "invalid_input", "内置菜谱不需要版本号。")
    elif str(recipe["version"]) != payload.get("recipe_version"):
        raise inventory_service.InventoryError(409, "version_conflict", "菜谱已变化，请刷新后重试。")
    missing = set(recipe["ingredients"]) - covered
    if missing:
        raise inventory_service.InventoryError(422, "invalid_input", "请填写每种食材的实际用量。")
    return inventory_service.apply_action(actor, action_payload)


def save_family_recipe(actor, cleaned, *, existing=None):
    """Persist a validated form; creation retries reuse the same request UUID."""
    inventory_service._require_member(actor)
    fields = {
        "title": cleaned["title"], "ingredients": cleaned["ingredients_text"],
        "steps": cleaned["steps_text"], "category": cleaned["category"],
        "tags": cleaned["tags_text"], "source_type": cleaned["source_type"],
        "source_url": cleaned["source_url"], "source_note": cleaned["source_note"],
    }
    digest = hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    try:
        with transaction.atomic():
            if existing is None:
                original = FamilyRecipe.objects.filter(created_by=actor, create_request_id=cleaned["request_id"]).first()
                if original is not None:
                    if original.create_digest != digest:
                        raise inventory_service.InventoryError(409, "idempotency_conflict", "该请求编号已用于其他菜谱内容。")
                    return original
                return FamilyRecipe.objects.create(created_by=actor, create_request_id=cleaned["request_id"], create_digest=digest, **fields)
            recipe = FamilyRecipe.objects.filter(pk=existing.pk).first()
            if recipe is None:
                raise inventory_service.InventoryError(404, "not_found", "菜谱不存在。")
            if recipe.version != cleaned["version"]:
                raise inventory_service.InventoryError(409, "version_conflict", "菜谱已变化，请刷新后重试。")
            for name, value in fields.items():
                setattr(recipe, name, value)
            # The legacy free-text editor cannot maintain structured quantities and steps.
            # Keep the old structured snapshot for review, but stop using it for matching.
            recipe.review_state = "needs_review"
            recipe.version += 1
            recipe.updated_at = timezone.now()
            recipe.save(update_fields=[*fields, "review_state", "version", "updated_at"])
            return recipe
    except OperationalError as exc:
        if inventory_service._is_busy(exc):
            raise inventory_service.InventoryError(503, "database_busy", "数据库暂时繁忙，请稍后用原表单重试。") from exc
        raise
