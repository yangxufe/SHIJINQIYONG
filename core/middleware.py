from django.http import JsonResponse
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

from core.security import has_role


class AuthenticationGateMiddleware:
    """Deny every application URL except login, health and local static."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in {reverse("login"), reverse("health")}:
            return self.get_response(request)
        if not request.user.is_authenticated:
            if request.path.startswith("/api/"):
                return JsonResponse({"error": {"code": "unauthenticated", "message": "请先登录。"}}, status=401)
            return redirect_to_login(request.get_full_path(), login_url=reverse("login"))
        if not (has_role(request.user, "admin") or has_role(request.user, "member")):
            if request.path.startswith("/api/"):
                return JsonResponse({"error": {"code": "forbidden", "message": "没有访问权限。"}}, status=403)
            from django.http import HttpResponseForbidden

            return HttpResponseForbidden("没有访问权限。")
        return self.get_response(request)


class ResponsePolicyMiddleware:
    """Protect dynamic responses without exposing runtime details."""

    CSP = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Cache-Control"] = "no-store"
        response["Content-Security-Policy"] = self.CSP
        response["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        return response
