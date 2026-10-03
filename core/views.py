from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.core import signing
from django.db import IntegrityError, OperationalError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from django.utils import timezone
from datetime import timedelta

from core.security import admin_required, has_role
from core.forms import INVITATION_SALT, MemberRegistrationForm
from core.models import HouseholdSettings, MemberInvitation, MemberRole
from inventory import today as today_service
from inventory.services import _is_busy


login_view = LoginView.as_view(template_name="core/login.html", redirect_authenticated_user=True)
logout_view = LogoutView.as_view(next_page="login")


@require_GET
def welcome(request):
    if request.user.is_authenticated:
        return redirect("index")
    return render(request, "core/welcome.html")


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = MemberRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        # Password hashing uses Django and occurs before the short write transaction.
        user = form.save(commit=False)
        invitation = form.cleaned_data["invitation"]
        try:
            with transaction.atomic():
                current = MemberInvitation.objects.get(pk=invitation.pk)
                if current.used_by_id or current.expires_at <= timezone.now() or not has_role(current.created_by, "admin"):
                    form.add_error("invitation", "邀请码已使用或已过期。")
                else:
                    user.save()
                    MemberRole.objects.create(user=user, role=MemberRole.Role.MEMBER)
                    current.used_by = user
                    current.save(update_fields=["used_by"])
                    messages.success(request, "注册成功，请使用新成员账号登录。")
                    return redirect("login")
        except IntegrityError:
            form.add_error(None, "账号或邀请码已被使用，请核对后重试。")
        except OperationalError as exc:
            if not _is_busy(exc):
                raise
            form.add_error(None, "服务器暂时繁忙，请稍后重试。")
            return render(request, "core/register.html", {"form": form}, status=503)
    return render(request, "core/register.html", {"form": form},
                  status=422 if request.method == "POST" else 200)


@require_GET
def index(request):
    return render(request, "core/index.html", today_service.get_today(request.user))


@require_GET
def today_api(request):
    return JsonResponse(today_service.get_today(request.user))


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_http_methods(["GET", "POST"])
def household_settings(request):
    token = ""
    error = ""
    if request.method == "POST":
        if not has_role(request.user, "admin"):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        if (set(request.POST) - {"csrfmiddlewaretoken", "create_invitation"}
                or any(len(request.POST.getlist(key)) != 1 for key in request.POST)
                or request.POST.get("create_invitation") != "yes"):
            error = "设置表单无效。"
        else:
            with transaction.atomic():
                if MemberInvitation.objects.filter(used_by__isnull=True, expires_at__gt=timezone.now()).count() >= 20:
                    error = "已有 20 个有效邀请，请先使用或等待过期。"
                else:
                    invitation = MemberInvitation.objects.create(created_by=request.user,
                        expires_at=timezone.now() + timedelta(hours=24))
                    token = signing.dumps(str(invitation.pk), salt=INVITATION_SALT)
    return render(request, "core/settings.html", {"household": HouseholdSettings.objects.first(),
        "invitation_token": token, "error": error}, status=422 if error else 200)


@admin_required
@require_GET
def household_settings_api(request):
    return JsonResponse({"error": {"code": "not_configured", "message": "家庭设置尚未配置。"}}, status=501)


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": {"code": "csrf_failed", "message": "请求未通过验证，请刷新页面后重试。"}}, status=403)
    return render(request, "403_csrf.html", status=403)
