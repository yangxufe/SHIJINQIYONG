"""Explicit confirmation of meal intent and private taste settings."""

from __future__ import annotations

import re
from uuid import uuid4

from django import forms

from meals.workbench import parse_request_text, validate_conditions


GOALS = (("high_protein", "偏高蛋白"), ("high_carbohydrate", "偏高碳水"), ("low_carbohydrate", "偏低碳水"),
         ("low_added_sugar", "少添加糖"), ("limit_total_sugar", "限制总糖"))
EQUIPMENT = (("炒锅", "炒锅"), ("汤锅", "汤锅"), ("电饭煲", "电饭煲"), ("蒸锅", "蒸锅"), ("烤箱", "烤箱"),
             ("砧板", "砧板"), ("菜刀", "菜刀"), ("碗", "碗"), ("量杯", "量杯"), ("食物温度计", "食物温度计"))


def split_names(value):
    return [part.strip() for part in re.split(r"[\n,，、]+", value or "") if part.strip()]


class RecipeConditionsForm(forms.Form):
    request_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)
    raw_text = forms.CharField(label="这餐想怎么吃", required=False, max_length=600, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "例如：两个人，健身后想吃高蛋白、高碳水、少添加糖，半小时左右"}))
    people = forms.IntegerField(label="用餐人数", min_value=1, max_value=12, initial=2)
    meal_type = forms.ChoiceField(label="安排方式", choices=(("single", "单道菜"), ("menu", "一餐多道菜")))
    stock_mode = forms.ChoiceField(label="食材模式", choices=(("strict", "严格只用现有食材"), ("buy", "允许补购缺口")))
    taste_mode = forms.ChoiceField(label="口味模式", choices=(("usual", "按平时口味"), ("gentle", "熟悉口味小幅变化"), ("explore", "尝试新口味")))
    goals = forms.MultipleChoiceField(label="营养方向", required=False, choices=GOALS, widget=forms.CheckboxSelectMultiple)
    excluded = forms.CharField(label="本餐明确排除的食材", required=False, max_length=400, help_text="逗号分隔；过敏或禁食请也保存到个人配置")
    equipment = forms.MultipleChoiceField(label="确实可用的器材", required=False, choices=EQUIPMENT, widget=forms.CheckboxSelectMultiple)
    priority_names = forms.CharField(label="优先消耗的食材", required=False, max_length=240)
    max_minutes = forms.IntegerField(label="希望总耗时（分钟）", min_value=5, max_value=1440, initial=30)
    must_meet_time = forms.BooleanField(label="时间必须满足", required=False)
    spice_max = forms.IntegerField(label="本餐辣度上限（0 不辣、5 很辣）", min_value=0, max_value=5, initial=1)
    skill = forms.ChoiceField(label="烹饪经验", choices=(("beginner", "新手"), ("regular", "会做家常菜"), ("experienced", "熟练")))
    explore_cuisine = forms.CharField(label="想尝试的菜系", required=False, max_length=40)
    participants = forms.CharField(label="其他用餐成员编号", required=False, max_length=120, help_text="仅合并对方明确授权分享的过敏和禁食限制；未授权的限制请手工核对")

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        try:
            participant_ids = [int(part) for part in re.split(r"[\s,，]+", data["participants"].strip()) if part]
            conditions = {
                "raw_text": data["raw_text"].strip(), "people": data["people"], "meal_type": data["meal_type"],
                "stock_mode": data["stock_mode"], "taste_mode": data["taste_mode"], "goals": data["goals"],
                "excluded": split_names(data["excluded"]), "equipment": data["equipment"],
                "priority_names": split_names(data["priority_names"]), "max_minutes": data["max_minutes"],
                "must_meet_time": data["must_meet_time"], "spice_max": data["spice_max"], "skill": data["skill"],
                "explore_cuisine": data["explore_cuisine"].strip(), "participants": participant_ids,
            }
            validate_conditions(conditions)
        except (ValueError, TypeError) as exc:
            raise forms.ValidationError(str(exc)) from exc
        data["conditions"] = conditions
        return data

    @staticmethod
    def interpreted_initial(data):
        parsed = parse_request_text(data.get("raw_text", ""))
        output = dict(data)
        if parsed["people"]:
            output["people"] = parsed["people"]
        if parsed["max_minutes"]:
            output["max_minutes"] = parsed["max_minutes"]
        if parsed["spice_max"] is not None:
            output["spice_max"] = parsed["spice_max"]
        if parsed["equipment"]:
            output["equipment"] = parsed["equipment"]
        output["goals"] = list(dict.fromkeys([*data.get("goals", []), *parsed["goals"]]))
        return output, parsed


class TasteProfileForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput, min_value=0)
    liked_cuisines = forms.CharField(label="喜欢的菜系", required=False, max_length=240)
    disliked_cuisines = forms.CharField(label="不喜欢的菜系", required=False, max_length=240)
    liked_ingredients = forms.CharField(label="喜欢的食材", required=False, max_length=400)
    disliked_ingredients = forms.CharField(label="不喜欢的食材", required=False, max_length=400)
    allergens = forms.CharField(label="过敏食材（硬限制）", required=False, max_length=400)
    forbidden = forms.CharField(label="禁食食材（硬限制）", required=False, max_length=400)
    spice_max = forms.IntegerField(label="可接受辣度上限", min_value=0, max_value=5, initial=1)
    tried_cuisines = forms.CharField(label="尝试过的菜系", required=False, max_length=240)
    made_methods = forms.CharField(label="做过的烹饪方式", required=False, max_length=240)
    liked_methods = forms.CharField(label="常用烹饪方式", required=False, max_length=240)
    available_equipment = forms.CharField(label="平时可用器材", required=False, max_length=240)
    disliked_tastes = forms.CharField(label="不喜欢的味道（酸、甜、咸、麻等）", required=False, max_length=240)
    liked_tastes = forms.CharField(label="喜欢的味道（酸、甜、咸、麻等）", required=False, max_length=240)
    explore_cuisines = forms.CharField(label="想探索的菜系", required=False, max_length=240)
    willing_to_explore = forms.BooleanField(label="愿意尝试新口味", required=False)
    share_restrictions = forms.BooleanField(label="允许同餐成员读取我的过敏/禁食限制", required=False)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        names = ("liked_cuisines", "disliked_cuisines", "liked_ingredients", "disliked_ingredients", "allergens", "forbidden", "tried_cuisines", "made_methods", "liked_methods", "available_equipment", "disliked_tastes", "liked_tastes", "explore_cuisines")
        result = {name: split_names(data[name]) for name in names}
        result["spice_max"] = data["spice_max"]
        result["willing_to_explore"] = data["willing_to_explore"]
        if any(len(values) > 20 or any(len(item) > 80 for item in values) for values in result.values() if isinstance(values, list)):
            raise forms.ValidationError("每组最多20项，每项最多80字。")
        data["profile_data"] = result
        return data
