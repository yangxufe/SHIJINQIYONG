"""Recipes written or saved by members of the single household."""

from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q


class FamilyRecipe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    title = models.CharField(max_length=80)
    ingredients = models.JSONField(default=list)
    steps = models.JSONField(default=list)
    category = models.CharField(max_length=20, default="家常菜")
    tags = models.JSONField(default=list)
    source_type = models.CharField(max_length=12, default="own")
    source_url = models.URLField(max_length=600, blank=True)
    source_note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="family_recipes")
    create_request_id = models.UUIDField()
    create_digest = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    structured_data = models.JSONField(default=dict, blank=True)
    review_state = models.CharField(max_length=16, default="needs_review")

    class Meta:
        ordering = ["-updated_at", "-created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["created_by", "create_request_id"], name="unique_family_recipe_request"),
        ]


class RecipeMedia(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "图片"
        VIDEO = "video", "视频"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    recipe = models.ForeignKey(FamilyRecipe, on_delete=models.CASCADE, related_name="media")
    kind = models.CharField(max_length=5, choices=Kind.choices)
    file_key = models.CharField(max_length=50, unique=True)
    mime_type = models.CharField(max_length=20)
    size_bytes = models.PositiveBigIntegerField()
    caption = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recipe_media")
    upload_request_id = models.UUIDField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["recipe"], condition=Q(kind="video"), name="one_video_per_recipe"),
            models.UniqueConstraint(fields=["created_by", "upload_request_id"], name="unique_recipe_media_request"),
        ]


class TasteProfile(models.Model):
    """Private member preferences; explicit sharing is required for meal participants."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="taste_profile")
    data = models.JSONField(default=dict)
    share_restrictions = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class HouseholdTaste(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    data = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="one_household_taste")]


class NutritionReference(models.Model):
    """Source-traceable values per 100 g edible portion; null is unknown."""

    ingredient_name = models.CharField(max_length=80)
    food_state = models.CharField(max_length=16, default="raw")
    source_name = models.CharField(max_length=80)
    source_id = models.CharField(max_length=80)
    source_url = models.URLField(max_length=600)
    source_version = models.CharField(max_length=40)
    edible_note = models.CharField(max_length=160, blank=True)
    energy_kcal = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    protein_g = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    carbohydrate_g = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    fat_g = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    total_sugar_g = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    added_sugar_g = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    checked_at = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ingredient_name", "food_state"], name="unique_nutrition_food_state")]


class RecipeRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipe_requests")
    request_id = models.UUIDField()
    digest = models.CharField(max_length=64)
    raw_text = models.TextField(blank=True)
    conditions = models.JSONField()
    inventory_signature = models.CharField(max_length=64)
    preference_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "request_id"], name="unique_recipe_request")]


class MenuPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="menu_plans")
    recipe_request = models.ForeignKey(RecipeRequest, on_delete=models.PROTECT, related_name="menus")
    recipe_ids = models.JSONField(default=list)
    executed_action = models.OneToOneField("inventory.BusinessAction", null=True, blank=True,
                                           on_delete=models.PROTECT, related_name="executed_menu")
    actual_nutrition = models.JSONField(default=dict, blank=True)
    actual_uses = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MenuShoppingContribution(models.Model):
    menu = models.ForeignKey(MenuPlan, on_delete=models.PROTECT, related_name="shopping_contributions")
    menu_version = models.PositiveIntegerField()
    ingredient_name = models.CharField(max_length=80)
    unit = models.CharField(max_length=10)
    shopping_item = models.OneToOneField("shopping.ShoppingItem", on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["menu", "menu_version", "ingredient_name", "unit"], name="unique_menu_purchase_gap")]


class RecipeFeedback(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipe_feedback")
    recipe_key = models.CharField(max_length=80)
    verdict = models.CharField(max_length=16)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "recipe_key"], name="unique_recipe_feedback")]


class GenerationTask(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        RUNNING = "running", "生成中"
        VALIDATING = "validating", "校验中"
        SUCCESS = "success", "已完成"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"
        TIMED_OUT = "timed_out", "超时"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="generation_tasks")
    recipe_request = models.ForeignKey(RecipeRequest, on_delete=models.PROTECT, related_name="generation_tasks")
    request_id = models.UUIDField()
    digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    provider = models.CharField(max_length=20)
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    deadline_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "request_id"], name="unique_generation_request")]
        indexes = [models.Index(fields=["status", "created_at"], name="generation_queue_idx")]
