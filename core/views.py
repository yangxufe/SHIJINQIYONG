from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.security import admin_required
from inventory import today as today_service


login_view = LoginView.as_view(template_name="core/login.html", redirect_authenticated_user=True)
logout_view = LogoutView.as_view(next_page="login")


@require_GET
def index(request):
    return render(request, "core/index.html", today_service.get_today(request.user))


@require_GET
def today_api(request):
    return JsonResponse(today_service.get_today(request.user))


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@admin_required
@require_GET
def household_settings(request):
    return render(request, "core/settings.html")


@admin_required
@require_GET
def household_settings_api(request):
    return JsonResponse({"error": {"code": "not_configured", "message": "家庭设置尚未配置。"}}, status=501)


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": {"code": "csrf_failed", "message": "请求未通过验证，请刷新页面后重试。"}}, status=403)
    return render(request, "403_csrf.html", status=403)
