"""Explainable, quantity-aware matching over the existing inventory facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from inventory.availability import usable_lots
from inventory.models import IngredientAlias, InventoryLot
from inventory.services import format_amount, parse_amount
from meals.catalog import load_catalog
from meals.models import FamilyRecipe, NutritionReference, TasteProfile, HouseholdTaste
from meals.structured import load_structured_catalog, validate_spec


BASE_UNIT = {"g": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "l": ("ml", 1000), "piece": ("piece", 1), "pack": ("pack", 1)}
NUTRIENTS = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g", "total_sugar_g", "added_sugar_g")


def canonical_name(name):
    catalog_alias = load_catalog()[1].get(name, name)
    alias = IngredientAlias.objects.select_related("ingredient").filter(name=catalog_alias).first()
    return alias.ingredient.name if alias else catalog_alias


def parse_request_text(value):
    """Extract only literal intent; unresolved text stays visible for confirmation."""
    if not isinstance(value, str) or len(value) > 600 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
        raise ValueError("需求文字过长或无效")
    extracted = {"raw_text": value.strip(), "goals": [], "people": None, "max_minutes": None, "spice_max": None, "equipment": []}
    for phrase, goal in (("高蛋白", "high_protein"), ("高碳水", "high_carbohydrate"), ("低碳水", "low_carbohydrate"), ("少添加糖", "low_added_sugar"), ("限制总糖", "limit_total_sugar")):
        if phrase in value:
            extracted["goals"].append(goal)
    for text, count in (("一个人", 1), ("两个人", 2), ("三个人", 3), ("四个人", 4)):
        if text in value:
            extracted["people"] = count
    match = re.search(r"([1-9])\s*人", value)
    if match:
        extracted["people"] = int(match.group(1))
    match = re.search(r"([1-9][0-9]?)\s*分(?:钟|钟)", value)
    if match:
        extracted["max_minutes"] = int(match.group(1))
    elif "半小时" in value:
        extracted["max_minutes"] = 30
    if "不太辣" in value or "微辣" in value:
        extracted["spice_max"] = 1
    if "只能用" in value or "只有" in value:
        extracted["equipment"] = [name for name in ("炒锅", "汤锅", "电饭煲", "蒸锅", "烤箱", "砧板", "菜刀", "碗", "量杯") if name in value]
    return extracted


def validate_conditions(raw):
    if not isinstance(raw, dict):
        raise ValueError("条件必须是对象")
    allowed = {"raw_text", "people", "meal_type", "stock_mode", "taste_mode", "goals", "excluded", "equipment", "max_minutes", "skill", "spice_max", "priority_names", "participants", "explore_cuisine", "must_meet_time"}
    if set(raw) != allowed:
        raise ValueError("条件字段不完整或含未知字段")
    if type(raw["people"]) is not int or not 1 <= raw["people"] <= 12:
        raise ValueError("用餐人数应为1至12人")
    if raw["meal_type"] not in {"single", "menu"} or raw["stock_mode"] not in {"strict", "buy"} or raw["taste_mode"] not in {"usual", "gentle", "explore"}:
        raise ValueError("用餐、食材或口味模式无效")
    if raw["skill"] not in {"beginner", "regular", "experienced"}:
        raise ValueError("熟练程度无效")
    if type(raw["max_minutes"]) is not int or not 5 <= raw["max_minutes"] <= 1440 or type(raw["spice_max"]) is not int or not 0 <= raw["spice_max"] <= 5:
        raise ValueError("时间或辣度无效")
    if type(raw["must_meet_time"]) is not bool:
        raise ValueError("时间约束无效")
    if not isinstance(raw["raw_text"], str) or len(raw["raw_text"]) > 600:
        raise ValueError("需求文字无效")
    for key, maximum in (("goals", 8), ("excluded", 20), ("equipment", 15), ("priority_names", 12), ("participants", 12)):
        values = raw[key]
        if not isinstance(values, list) or len(values) > maximum or len(set(map(str, values))) != len(values):
            raise ValueError(f"{key}无效")
    allowed_goals = {"high_protein", "high_carbohydrate", "low_carbohydrate", "low_added_sugar", "limit_total_sugar"}
    if any(goal not in allowed_goals for goal in raw["goals"]):
        raise ValueError("营养方向无效")
    if "high_carbohydrate" in raw["goals"] and "low_carbohydrate" in raw["goals"]:
        raise ValueError("高碳水与低碳水相互冲突，请选择其中一项")
    for key in ("excluded", "equipment", "priority_names"):
        if any(not isinstance(item, str) or not item.strip() or len(item) > 80 for item in raw[key]):
            raise ValueError(f"{key}内容无效")
    if any(type(item) is not int or item < 1 for item in raw["participants"]):
        raise ValueError("用餐成员编号无效")
    if not isinstance(raw["explore_cuisine"], str) or len(raw["explore_cuisine"]) > 40:
        raise ValueError("尝新菜系无效")
    return raw


def effective_taste(actor, conditions):
    household = HouseholdTaste.objects.filter(pk=1).first()
    personal = TasteProfile.objects.filter(user=actor).first()
    data = dict(household.data if household else {})
    data.update(personal.data if personal else {})
    # A softer personal preference must never erase a household hard restriction.
    restrictions = set(conditions["excluded"])
    for source in (household.data if household else {}, personal.data if personal else {}):
        restrictions.update(source.get("allergens", []))
        restrictions.update(source.get("forbidden", []))
    for member in TasteProfile.objects.filter(user_id__in=conditions["participants"], share_restrictions=True).exclude(user=actor):
        restrictions.update(member.data.get("allergens", []))
        restrictions.update(member.data.get("forbidden", []))
    return data, restrictions, personal.version if personal else 0


def specs_for_actor(actor):
    specs = dict(load_structured_catalog())
    for recipe in FamilyRecipe.objects.all():
        if recipe.review_state in {"reviewed", "machine_checked"} and recipe.structured_data:
            try:
                spec = validate_spec(recipe.structured_data)
            except ValueError:
                continue
            specs[f"family-{recipe.pk}"] = {**spec, "id": f"family-{recipe.pk}", "source_label": "家庭结构化菜谱"}
    return specs


def inventory_signature():
    rows = list(InventoryLot.objects.order_by("pk").values_list("pk", "version", "quantity_milli", "status", "storage_status", "package_date_status", "package_date"))
    return hashlib.sha256(json.dumps(rows, default=str, separators=(",", ":")).encode()).hexdigest()


def _available_lots():
    lots = list(usable_lots())
    lots.sort(key=lambda lot: (lot.planned_use_date is None, lot.planned_use_date or timezone.localdate(), not lot.manual_priority, lot.quantity_milli, lot.pk))
    return lots


def _scale_amount(amount, servings, base_servings):
    value = Decimal(amount) * Decimal(servings) / Decimal(base_servings)
    milli = value * 1000
    if milli != milli.to_integral_value():
        raise ValueError("份数换算超过库存支持的三位小数精度")
    return int(milli)


def calculate_nutrition(specs, servings):
    total = {key: Decimal(0) for key in NUTRIENTS}
    unknown = {key: [] for key in NUTRIENTS}
    references = {}
    for spec in specs:
        for item in spec["ingredients"]:
            name = canonical_name(item["name"])
            quantity = Decimal(item["quantity"]) * Decimal(servings) / Decimal(spec["servings"])
            unit = item["unit"]
            if unit == "kg":
                quantity *= 1000
                unit = "g"
            if unit != "g":
                for key in NUTRIENTS:
                    unknown[key].append(name + "（无可靠克重）")
                continue
            reference = NutritionReference.objects.filter(ingredient_name=name, food_state=item["food_state"]).first()
            if reference is None:
                for key in NUTRIENTS:
                    unknown[key].append(name)
                continue
            references[name] = {"source": reference.source_name, "id": reference.source_id, "url": reference.source_url, "state": reference.food_state}
            for key in NUTRIENTS:
                value = getattr(reference, key)
                if value is None:
                    unknown[key].append(name)
                else:
                    total[key] += value * quantity / 100
    return {"whole": {key: str(total[key].quantize(Decimal("0.01"))) if not unknown[key] else None for key in NUTRIENTS},
            "per_person": {key: str((total[key] / servings).quantize(Decimal("0.01"))) if not unknown[key] else None for key in NUTRIENTS},
            "unknown": unknown, "references": references, "estimated": True}


def calculate_actual_nutrition(specs, action_items, servings):
    """Recalculate from committed ledger deltas, never reuse planned nutrition."""
    states = defaultdict(set)
    for spec in specs:
        for item in spec["ingredients"]:
            states[canonical_name(item["name"])].add(item["food_state"])
    ids = [item["lot_id"] for item in action_items]
    lots = {lot.pk: lot for lot in InventoryLot.objects.select_related("ingredient").filter(pk__in=ids)}
    total = {key: Decimal(0) for key in NUTRIENTS}
    unknown = {key: [] for key in NUTRIENTS}
    references = {}
    for item in action_items:
        lot = lots[item["lot_id"]]
        name = canonical_name(lot.ingredient.name)
        state = next(iter(states[name])) if len(states[name]) == 1 else None
        amount = -Decimal(item["change"])
        if lot.unit == "kg":
            amount *= 1000
        if lot.unit not in {"g", "kg"} or state is None:
            for key in NUTRIENTS:
                unknown[key].append(name + "（无可靠克重或状态）")
            continue
        reference = NutritionReference.objects.filter(ingredient_name=name, food_state=state).first()
        if reference is None:
            for key in NUTRIENTS:
                unknown[key].append(name)
            continue
        references[name] = {"source": reference.source_name, "id": reference.source_id,
                            "url": reference.source_url, "state": state}
        for key in NUTRIENTS:
            value = getattr(reference, key)
            if value is None:
                unknown[key].append(name)
            else:
                total[key] += value * amount / 100
    return {"whole": {key: str(total[key].quantize(Decimal("0.01"))) if not unknown[key] else None for key in NUTRIENTS},
            "per_person": {key: str((total[key] / servings).quantize(Decimal("0.01"))) if not unknown[key] else None for key in NUTRIENTS},
            "unknown": unknown, "references": references, "estimated": True}


def evaluate_menu(specs, *, servings, conditions, actor=None, lots=None):
    """Allocate selected recipes jointly; alternatives call this separately."""
    validate_conditions(conditions)
    if not 1 <= len(specs) <= 4:
        raise ValueError("菜单应有1至4道菜")
    taste, forbidden, _ = effective_taste(actor, conditions) if actor is not None else ({}, set(conditions["excluded"]), 0)
    if lots is None:
        lots = _available_lots()
    remaining = {lot.pk: lot.quantity_milli * BASE_UNIT[lot.unit][1] for lot in lots}
    by_name = defaultdict(list)
    for lot in lots:
        by_name[canonical_name(lot.ingredient.name)].append(lot)
    allocations, gaps, used_names, blockers, coverage_ratios = [], [], set(), [], []
    for spec in specs:
        if any(canonical_name(row["name"]) in forbidden for row in spec["ingredients"]):
            blockers.append(f"{spec['title']}含本餐排除或共享禁食食材")
        if spec["spice_level"] > min(conditions["spice_max"], taste.get("spice_max", 5)):
            blockers.append(f"{spec['title']}超过明确辣度上限")
        missing_equipment = sorted(set(spec["equipment"]) - set(conditions["equipment"]))
        if missing_equipment:
            blockers.append(f"{spec['title']}缺少器材：{'、'.join(missing_equipment)}")
        if conditions["must_meet_time"] and spec["total_minutes"] > conditions["max_minutes"]:
            blockers.append(f"{spec['title']}超过必须满足的总耗时")
        for row in spec["ingredients"]:
            name = canonical_name(row["name"])
            try:
                needed = _scale_amount(row["quantity"], servings, spec["servings"])
            except ValueError:
                blockers.append(f"{spec['title']}的{name}无法按当前人数精确换算，请调整份数")
                continue
            unit, factor = BASE_UNIT[row["unit"]]
            needed_base = needed * factor
            open_base = needed_base
            used_names.add(name)
            for lot in by_name[name]:
                lot_unit, _ = BASE_UNIT[lot.unit]
                if lot_unit != unit or not remaining[lot.pk]:
                    continue
                # A lot can only be debited to its own three-decimal unit precision.
                lot_factor = BASE_UNIT[lot.unit][1]
                taken = (min(open_base, remaining[lot.pk]) // lot_factor) * lot_factor
                if taken:
                    allocations.append({"recipe_id": spec["id"], "ingredient": name, "lot_id": lot.pk, "lot_version": lot.version,
                                        "quantity": format_amount(taken // lot_factor),
                                        "unit": lot.unit, "remaining": str(Decimal(remaining[lot.pk] - taken) / 1000 / BASE_UNIT[lot.unit][1])})
                    remaining[lot.pk] -= taken
                    open_base -= taken
                if not open_base:
                    break
            if open_base:
                gaps.append({"recipe_id": spec["id"], "ingredient": name, "quantity": format_amount(open_base), "unit": unit,
                             "reason": "库存数量不足或单位未能可靠换算"})
            coverage_ratios.append(1 - open_base / needed_base)
    feasible = not blockers and (conditions["stock_mode"] == "buy" or not gaps)
    priority_lots = [lot for lot in lots if lot.manual_priority or lot.planned_use_date]
    priority_unused = [f"批次 #{lot.pk} {lot.ingredient.name} 仍有 {format_amount(remaining[lot.pk] // BASE_UNIT[lot.unit][1])} {lot.unit}"
                       for lot in priority_lots if remaining[lot.pk] > 0]
    priority_progress = sum((lot.quantity_milli * BASE_UNIT[lot.unit][1] - remaining[lot.pk]) /
                            (lot.quantity_milli * BASE_UNIT[lot.unit][1]) for lot in priority_lots if lot.quantity_milli)
    priority_used = sum(1 for lot in priority_lots if remaining[lot.pk] < lot.quantity_milli * BASE_UNIT[lot.unit][1])
    coverage = sum(coverage_ratios) / len(coverage_ratios) if coverage_ratios else 0
    cuisine = specs[0]["cuisine"]
    liked = cuisine in taste.get("liked_cuisines", [])
    explore = conditions["taste_mode"] == "explore" and (not conditions["explore_cuisine"] or cuisine == conditions["explore_cuisine"])
    if conditions["taste_mode"] == "explore":
        taste_points = 5 if explore and conditions["explore_cuisine"] else (2 if explore else -1)
    else:
        taste_points = 3 if liked else (-2 if cuisine in taste.get("disliked_cuisines", []) else 0)
    score = int(priority_progress * 10) + int(coverage * 10) + taste_points - (len(gaps) * 4) - max(0, specs[0]["total_minutes"] - conditions["max_minutes"]) // 10
    reasons = []
    if priority_used:
        reasons.append(f"已使用{priority_used}个优先批次，仍需核对各批次剩余量")
    reasons.append(f"按材料所需量平均覆盖约{int(coverage * 100)}%，净缺口{len(gaps)}种")
    if explore:
        reasons.append("符合本次尝新方向")
    elif liked:
        reasons.append("符合平时菜系偏好")
    return {"feasible": feasible, "blockers": blockers, "allocations": allocations, "gaps": gaps,
            "priority_unused": list(dict.fromkeys(priority_unused)), "score": score, "reasons": reasons,
            "nutrition": calculate_nutrition(specs, servings)}


def ranked_candidates(actor, conditions):
    validate_conditions(conditions)
    specs = specs_for_actor(actor)
    lots = _available_lots()
    evaluated = []
    for spec in specs.values():
        result = evaluate_menu([spec], servings=conditions["people"], conditions=conditions, actor=actor, lots=lots)
        if result["feasible"]:
            evaluated.append({"spec": spec, "match": result})
    # Directional goals rank *known* values only among this candidate set. No universal targets are invented.
    for goal, nutrient, reverse in (("high_protein", "protein_g", True),
                                     ("high_carbohydrate", "carbohydrate_g", True),
                                     ("low_carbohydrate", "carbohydrate_g", False),
                                     ("low_added_sugar", "added_sugar_g", False),
                                     ("limit_total_sugar", "total_sugar_g", False)):
        if goal not in conditions["goals"]:
            continue
        known = [row for row in evaluated if row["match"]["nutrition"]["per_person"][nutrient] is not None]
        if not known:
            for row in evaluated:
                row["match"]["reasons"].append(f"{goal}：营养数据未核算，未判定达标")
            continue
        known.sort(key=lambda row: Decimal(row["match"]["nutrition"]["per_person"][nutrient]), reverse=reverse)
        for index, row in enumerate(known):
            row["match"]["score"] += max(0, len(known) - index)
            row["match"]["reasons"].append(f"{goal}：按本批候选已核算的每人{nutrient}相对排序")
    evaluated.sort(key=lambda row: (-row["match"]["score"], row["spec"]["title"]))
    return evaluated
