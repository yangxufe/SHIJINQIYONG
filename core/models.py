from django.conf import settings
from django.db import models
from django.db.models import Q
from uuid import uuid4


class MemberRole(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        MEMBER = "member", "成员"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member_role")
    role = models.CharField(max_length=16, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(role__in=["admin", "member"]), name="member_role_valid")]


class HouseholdSettings(models.Model):
    """The only household is row 1; creation remains an explicit later action."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    display_name = models.CharField(max_length=80, default="我的家庭")
    time_zone = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="one_household_row")]


class MemberInvitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="member_invitations")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_by = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                  null=True, blank=True, related_name="registration_invitation")
