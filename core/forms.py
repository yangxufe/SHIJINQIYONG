from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import MemberInvitation


INVITATION_SALT = "core.member-invitation.v1"


class MemberRegistrationForm(UserCreationForm):
    invitation = forms.CharField(label="家庭邀请码", max_length=300, strip=True,
                                 widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "off"}))

    def clean_invitation(self):
        token = self.cleaned_data["invitation"]
        try:
            identifier = signing.loads(token, salt=INVITATION_SALT, max_age=24 * 60 * 60)
            invitation = MemberInvitation.objects.filter(pk=identifier, used_by__isnull=True,
                expires_at__gt=timezone.now(), created_by__is_active=True,
                created_by__member_role__role="admin").first()
        except (signing.BadSignature, ValueError, TypeError, ValidationError):
            invitation = None
        if invitation is None:
            raise forms.ValidationError("邀请码无效、已使用或已过期，请联系家庭管理员。")
        return invitation
