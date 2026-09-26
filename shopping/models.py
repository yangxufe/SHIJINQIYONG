from django.db import models
from django.db.models import Q

from inventory.models import BusinessAction, Ingredient, InventoryLot


class ShoppingItem(models.Model):
    class Status(models.TextChoices):
        NEEDED = "needed", "待采购"
        BOUGHT = "bought", "已买到"
        RECEIVED = "received", "已入库"
        CANCELLED = "cancelled", "已取消"

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, null=True, blank=True)
    name = models.CharField(max_length=80)
    quantity_milli = models.BigIntegerField()
    unit = models.CharField(max_length=10, choices=InventoryLot.Unit.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEEDED)
    received_lot = models.OneToOneField(InventoryLot, on_delete=models.PROTECT, null=True, blank=True, related_name="shopping_source")
    received_action = models.OneToOneField(BusinessAction, on_delete=models.PROTECT, null=True, blank=True, related_name="shopping_receipt")
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_milli__gt=0), name="shopping_qty_positive"),
            models.CheckConstraint(condition=Q(unit__in=["g", "kg", "ml", "l", "piece", "pack"]), name="shopping_unit_valid"),
            models.CheckConstraint(condition=Q(status__in=["needed", "bought", "received", "cancelled"]), name="shopping_status_valid"),
            models.CheckConstraint(condition=Q(status="received", received_lot__isnull=False, received_action__isnull=False) | Q(status__in=["needed", "bought", "cancelled"], received_lot__isnull=True, received_action__isnull=True), name="shopping_received_has_result"),
        ]
        indexes = [models.Index(fields=["status", "-created_at"], name="shopping_status_recent_idx")]
