"""One household-day and food-availability rule for reading and cooking."""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import HouseholdSettings
from inventory.models import InventoryLot


def household_today():
    zone_name = HouseholdSettings.objects.filter(pk=1).values_list("time_zone", flat=True).first() or settings.TIME_ZONE
    return timezone.localdate(timezone=ZoneInfo(zone_name)), zone_name


def usable_lots():
    today, _ = household_today()
    expired = Q(package_date_status=InventoryLot.PackageDateStatus.KNOWN, package_date__lt=today)
    return InventoryLot.objects.select_related("ingredient").filter(
        status=InventoryLot.Status.ACTIVE,
        storage_status=InventoryLot.StorageStatus.VERIFIED,
        quantity_milli__gt=0,
    ).exclude(expired)
