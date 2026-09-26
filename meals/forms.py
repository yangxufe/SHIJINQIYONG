"""Small server-side form for household-authored and linked recipes."""

import re
import unicodedata

from django import forms

from meals.catalog import load_catalog


SOURCE_CHOICES = (
    ("own", "自己写的"),
    ("video", "视频教程"),
    ("article", "文字教程"),
    ("images", "图片教程"),
)


def _short_text(value, limit, label):
    value = unicodedata.normalize("NFC", value.strip())
    if not value or len(value) > limit or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise forms.ValidationError(f"{label}不能为空、超长或包含控制字符。")
    return value


class FamilyRecipeForm(forms.Form):
    title = forms.CharField(label="菜谱名称", max_length=80)
    ingredients_text = forms.CharField(label="主要食材（每行一种）", max_length=800, widget=forms.Textarea(attrs={"rows": 4}))
    steps_text = forms.CharField(label="做法（每行一步）", required=False, max_length=2600, widget=forms.Textarea(attrs={"rows": 6}))
    category = forms.CharField(label="分类", max_length=20, initial="家常菜")
    tags_text = forms.CharField(label="标签（逗号分隔）", required=False, max_length=150)
    source_type = forms.ChoiceField(label="教程类型", choices=SOURCE_CHOICES, initial="own")
    source_url = forms.URLField(label="原教程链接", required=False, max_length=600)
    source_note = forms.CharField(label="补充笔记", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
    request_id = forms.UUIDField(widget=forms.HiddenInput)
    version = forms.IntegerField(required=False, min_value=0, widget=forms.HiddenInput)

    def clean_title(self):
        return _short_text(self.cleaned_data["title"], 80, "菜谱名称")

    def clean_category(self):
        return _short_text(self.cleaned_data["category"], 20, "分类")

    def clean_ingredients_text(self):
        values = re.split(r"[\r\n、,，]+", self.cleaned_data["ingredients_text"])
        _, aliases = load_catalog()
        ingredients = [_short_text(value, 80, "食材名") for value in values if value.strip()]
        ingredients = [aliases.get(value, value) for value in ingredients]
        if not 1 <= len(ingredients) <= 12 or len(set(ingredients)) != len(ingredients):
            raise forms.ValidationError("请填写 1 至 12 种不重复的主要食材。")
        return ingredients

    def clean_steps_text(self):
        steps = [_short_text(value, 240, "做法") for value in self.cleaned_data["steps_text"].splitlines() if value.strip()]
        if len(steps) > 12:
            raise forms.ValidationError("做法最多 12 步。")
        return steps

    def clean_tags_text(self):
        values = re.split(r"[\r\n、,，]+", self.cleaned_data["tags_text"])
        tags = [_short_text(value, 16, "标签") for value in values if value.strip()]
        if len(tags) > 6 or len(tags) != len(set(tags)):
            raise forms.ValidationError("最多填写 6 个不重复标签。")
        return tags

    def clean_source_note(self):
        value = unicodedata.normalize("NFC", self.cleaned_data["source_note"].strip())
        if any(ord(char) < 32 and char not in "\r\n\t" for char in value):
            raise forms.ValidationError("笔记包含不支持的字符。")
        return value

    def clean(self):
        data = super().clean()
        source_type = data.get("source_type")
        source_url = data.get("source_url")
        if source_url and not source_url.startswith("https://"):
            self.add_error("source_url", "原教程链接必须使用 HTTPS。")
        if source_type == "own" and not data.get("steps_text"):
            self.add_error("steps_text", "自己写的菜谱请填写做法。")
        if source_type == "article" and not source_url and not data.get("steps_text"):
            self.add_error("steps_text", "文字教程请填写做法，或提供原页面链接。")
        return data
