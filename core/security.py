"""Small access policy helpers; Django owns authentication and sessions."""

from functools import wraps
from ipaddress import ip_address

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


def axes_client_ip(request):
    """Use Caddy's single overwritten XFF value only from the loopback hop."""
    peer = request.META.get("REMOTE_ADDR", "")
    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if peer_ip.is_loopback and forwarded and "," not in forwarded:
        try:
            return str(ip_address(forwarded.strip()))
        except ValueError:
            pass
    return str(peer_ip)


def has_role(user, role):
    if not user.is_authenticated or not user.is_active:
        return False
    profile = getattr(user, "member_role", None)
    return profile is not None and profile.role == role


def admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not has_role(request.user, "admin"):
            if request.path.startswith("/api/"):
                return JsonResponse({"error": {"code": "forbidden", "message": "仅家庭管理员可用。"}}, status=403)
            raise PermissionDenied("该操作仅家庭管理员可用。")
        return view(request, *args, **kwargs)

    return wrapped
