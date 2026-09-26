from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Ingredient(models.Model):
    name = models.CharField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class IngredientAlias(models.Model):
    name = models.CharField(max_length=80, unique=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="aliases")


class InventoryLot(models.Model):
    class Unit(models.TextChoices):
        GRAM = "g", "克"
        KILOGRAM = "kg", "千克"
        MILLILITER = "ml", "毫升"
        LITER = "l", "升"
        PIECE = "piece", "个"
        PACK = "pack", "包"

    class Location(models.TextChoices):
        FRIDGE = "fridge", "冷藏"
        FREEZER = "freezer", "冷冻"
        PANTRY = "pantry", "常温"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        ACTIVE = "active", "在库"
        SUSPECT = "suspect", "疑似变质"
        DISCARDED = "discarded", "已丢弃"
        DEPLETED = "depleted", "已用完"

    class StorageStatus(models.TextChoices):
        VERIFIED = "verified", "已核对"
        NEEDS_CHECK = "needs_check", "待核对"

    class PackageDateStatus(models.TextChoices):
        KNOWN = "known", "已记录"
        NOT_APPLICABLE = "not_applicable", "不适用"
        UNKNOWN = "unknown", "未记录"

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="lots")
    name = models.CharField(max_length=80)
    quantity_milli = models.BigIntegerField()
    unit = models.CharField(max_length=10, choices=Unit.choices)
    location = models.CharField(max_length=10, choices=Location.choices)
    planned_use_date = models.DateField(null=True, blank=True)
    package_date = models.DateField(null=True, blank=True)
    package_date_text = models.CharField(max_length=80, blank=True)
    package_date_status = models.CharField(max_length=16, choices=PackageDateStatus.choices, default=PackageDateStatus.UNKNOWN)
    purchase_date = models.DateField(null=True, blank=True)
    opened_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    storage_status = models.CharField(max_length=12, choices=StorageStatus.choices, default=StorageStatus.NEEDS_CHECK)
    manual_priority = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_milli__gte=0, quantity_milli__lte=1_000_000_000_000), name="lot_qty_bounded"),
            models.CheckConstraint(condition=Q(unit__in=["g", "kg", "ml", "l", "piece", "pack"]), name="lot_unit_valid"),
            models.CheckConstraint(condition=Q(location__in=["fridge", "freezer", "pantry", "other"]), name="lot_location_valid"),
            models.CheckConstraint(condition=Q(status__in=["active", "suspect", "discarded", "depleted"]), name="lot_status_valid"),
            models.CheckConstraint(condition=Q(storage_status__in=["verified", "needs_check"]), name="lot_storage_valid"),
            models.CheckConstraint(condition=Q(package_date_status__in=["known", "unknown", "not_applicable"]), name="lot_package_status_valid"),
            models.CheckConstraint(condition=Q(package_date_status="known", package_date__isnull=False) | Q(package_date_status__in=["unknown", "not_applicable"], package_date__isnull=True), name="lot_package_date_consistent"),
        ]
        indexes = [
            models.Index(fields=["status", "planned_use_date"], name="lot_status_planned_idx"),
            models.Index(fields=["ingredient", "status"], name="lot_ingredient_status_idx"),
        ]


class BusinessAction(models.Model):
    class Kind(models.TextChoices):
        LOT_CREATE = "lot_create", "录入"
        LOT_EDIT = "lot_edit", "编辑"
        CONSUME = "consume", "使用（旧类型）"
        COOK = "cook", "用于做饭"
        EAT = "eat", "直接食用"
        DISCARD = "discard", "丢弃"
        CORRECT = "correct", "库存校正"
        SHOP_ADD = "shop_add", "加入采购"
        SHOP_BOUGHT = "shop_bought", "标记买到"
        SHOP_CANCEL = "shop_cancel", "取消采购"
        SHOP_RECEIVE = "shop_receive", "采购入库"

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="business_actions")
    request_id = models.UUIDField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    params_hash = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor", "request_id"], name="action_actor_request_unique"),
            models.CheckConstraint(condition=Q(kind__in=["lot_create", "lot_edit", "consume", "cook", "eat", "discard", "correct", "shop_add", "shop_bought", "shop_cancel", "shop_receive"]), name="action_kind_valid"),
        ]
        indexes = [models.Index(fields=["actor", "-created_at"], name="action_actor_recent_idx")]


class Movement(models.Model):
    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name="movements")
    action = models.ForeignKey(BusinessAction, on_delete=models.PROTECT, related_name="movements")
    delta_milli = models.BigIntegerField()
    unit = models.CharField(max_length=10, choices=InventoryLot.Unit.choices)
    before_milli = models.BigIntegerField()
    after_milli = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(before_milli__gte=0, before_milli__lte=1_000_000_000_000), name="movement_before_bounded"),
            models.CheckConstraint(condition=Q(after_milli__gte=0, after_milli__lte=1_000_000_000_000), name="movement_after_bounded"),
            models.CheckConstraint(condition=Q(after_milli=F("before_milli") + F("delta_milli")), name="movement_balance_matches"),
            models.CheckConstraint(condition=Q(unit__in=["g", "kg", "ml", "l", "piece", "pack"]), name="movement_unit_valid"),
        ]
        indexes = [models.Index(fields=["lot", "-created_at"], name="movement_lot_recent_idx")]
