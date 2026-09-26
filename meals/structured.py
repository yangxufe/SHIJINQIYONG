"""Strict recipe structure shared by local content and untrusted model output."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from inventory.services import parse_amount
from meals.safety_rules import RULES


SPEC_KEYS = {"id", "title", "category", "cuisine", "servings", "difficulty", "spice_level", "prep_minutes", "active_minutes", "wait_minutes", "total_minutes", "equipment", "ingredients", "preparations", "steps", "safety_rule_ids", "source_label"}
INGREDIENT_KEYS = {"name", "quantity", "unit", "role", "food_state"}
STEP_KEYS = {"equipment", "uses", "action", "heat", "minutes_min", "minutes_max", "done_when", "tip"}
USE_KEYS = {"name", "quantity", "unit"}
UNITS = {"g", "kg", "ml", "l", "piece", "pack"}
FORBIDDEN = ("冲洗生鸡肉", "清洗生鸡肉", "洗涤剂清洗蔬果", "盐水浸泡消毒", "试吃判断安全", "变质后加热",
             "忽略之前指令", "忽略以上指令", "系统提示词", "开发者指令", "执行SQL", "执行命令")
SCHEMA_VERSION = 1


def _text(value, label, limit=240):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or re.search(r"[\x00-\x1f\x7f<>]", value):
        raise ValueError(f"{label}无效")
    if any(phrase in value for phrase in FORBIDDEN):
        raise ValueError(f"{label}含不安全操作")
    return value.strip()


def _integer(value, label, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{label}无效")
    return value


def validate_spec(raw):
    """Return a clean JSON-ready recipe or reject it; JSON shape alone is insufficient."""
    if not isinstance(raw, dict) or set(raw) != SPEC_KEYS:
        raise ValueError("菜谱字段不完整或含多余字段")
    spec = dict(raw)
    spec["id"] = _text(spec["id"], "菜谱编号", 80)
    spec["title"] = _text(spec["title"], "菜名", 80)
    for field in ("category", "cuisine", "difficulty", "source_label"):
        spec[field] = _text(spec[field], field, 40)
    for field, bounds in {"servings": (1, 12), "spice_level": (0, 5), "prep_minutes": (0, 240), "active_minutes": (1, 240), "wait_minutes": (0, 1440), "total_minutes": (1, 1440)}.items():
        spec[field] = _integer(spec[field], field, *bounds)
    if spec["total_minutes"] < max(spec["prep_minutes"], spec["active_minutes"], spec["wait_minutes"]):
        raise ValueError("总耗时小于必要阶段")
    if not isinstance(spec["equipment"], list) or not 1 <= len(spec["equipment"]) <= 12:
        raise ValueError("器材清单无效")
    spec["equipment"] = [_text(item, "器材", 40) for item in spec["equipment"]]
    if len(set(spec["equipment"])) != len(spec["equipment"]):
        raise ValueError("器材重复")
    if not isinstance(spec["ingredients"], list) or not 1 <= len(spec["ingredients"]) <= 20:
        raise ValueError("材料清单无效")
    ingredients = {}
    for row in spec["ingredients"]:
        if not isinstance(row, dict) or set(row) != INGREDIENT_KEYS:
            raise ValueError("材料字段无效")
        name = _text(row["name"], "材料名", 80)
        if name in ingredients or row["unit"] not in UNITS:
            raise ValueError("材料重复或单位无效")
        parse_amount(row["quantity"])
        ingredients[name] = dict(row, name=name, role=_text(row["role"], "材料角色", 20), food_state=_text(row["food_state"], "材料状态", 20))
    if not isinstance(spec["preparations"], list) or len(spec["preparations"]) > 30:
        raise ValueError("备料内容无效")
    for row in spec["preparations"]:
        if not isinstance(row, dict) or set(row) != {"name", "action"} or row["name"] not in ingredients:
            raise ValueError("备料引用无效")
        _text(row["action"], "备料说明", 240)
    if not isinstance(spec["steps"], list) or not 1 <= len(spec["steps"]) <= 24:
        raise ValueError("做法步骤无效")
    used = defaultdict(int)
    for step in spec["steps"]:
        if not isinstance(step, dict) or set(step) != STEP_KEYS or step["equipment"] not in spec["equipment"]:
            raise ValueError("步骤器材或字段无效")
        if not isinstance(step["uses"], list) or not step["uses"]:
            raise ValueError("步骤缺少材料")
        for item in step["uses"]:
            if not isinstance(item, dict) or set(item) != USE_KEYS or item["name"] not in ingredients:
                raise ValueError("步骤增加了材料表外食材")
            if item["unit"] != ingredients[item["name"]]["unit"]:
                raise ValueError("步骤材料单位不一致")
            used[item["name"]] += parse_amount(item["quantity"])
        for field in ("action", "heat", "done_when", "tip"):
            _text(step[field], field, 320)
        low = _integer(step["minutes_min"], "最短步骤时间", 0, 240)
        high = _integer(step["minutes_max"], "最长步骤时间", low, 240)
        if high == 0:
            raise ValueError("步骤耗时不能为零")
    for name, ingredient in ingredients.items():
        if used[name] != parse_amount(ingredient["quantity"]):
            raise ValueError(f"材料 {name} 的步骤用量与材料表不一致")
    if not isinstance(spec["safety_rule_ids"], list) or len(spec["safety_rule_ids"]) > 8:
        raise ValueError("安全规则引用无效")
    for rule_id in spec["safety_rule_ids"]:
        if rule_id not in RULES:
            raise ValueError("未知安全规则")
    if spec["safety_rule_ids"] and "食物温度计" not in spec["equipment"]:
        raise ValueError("需要核对中心温度的菜谱必须列出食物温度计")
    if any("鸡肉" in name or "鸡腿" in name for name in ingredients) and "poultry_74c" not in spec["safety_rule_ids"]:
        raise ValueError("鸡肉菜谱缺少温度规则")
    if any(any(word in name for word in ("鸭肉", "鹅肉", "火鸡")) for name in ingredients) and "poultry_74c" not in spec["safety_rule_ids"]:
        raise ValueError("禽肉菜谱缺少温度规则")
    if any("鸡蛋" in name for name in ingredients) and "egg_71c" not in spec["safety_rule_ids"]:
        raise ValueError("蛋类菜谱缺少温度规则")
    if any(any(word in name for word in ("肉末", "肉馅", "绞肉")) for name in ingredients) and "ground_meat_71c" not in spec["safety_rule_ids"]:
        raise ValueError("绞肉菜谱缺少温度规则")
    if any("鱼" in name for name in ingredients) and "fish_63c" not in spec["safety_rule_ids"]:
        raise ValueError("鱼类菜谱缺少温度规则")
    if any(any(word in name for word in ("牛肉", "猪肉", "羊肉")) for name in ingredients) and not ({"ground_meat_71c", "whole_meat_63c_rest3"} & set(spec["safety_rule_ids"])):
        raise ValueError("肉类菜谱缺少温度和静置规则")
    return spec


@lru_cache(maxsize=1)
def load_structured_catalog():
    path = Path(__file__).resolve().parent / "data" / "structured_recipes.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if set(document) != {"schema_version", "recipes"} or document["schema_version"] != SCHEMA_VERSION:
        raise ValueError("结构化菜谱版本无效")
    recipes = [validate_spec(item) for item in document["recipes"]]
    if len({item["id"] for item in recipes}) != len(recipes):
        raise ValueError("结构化菜谱编号重复")
    return {item["id"]: item for item in recipes}
