"""LAN deployment settings. Fail closed when required configuration is absent."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def _csv_env(name: str) -> list[str]:
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


ALLOWED_HOSTS = _csv_env("SHIJIN_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _csv_env("SHIJIN_CSRF_TRUSTED_ORIGINS")
STATIC_ROOT = Path(os.environ.get("SHIJIN_STATIC_ROOT", BASE_DIR / "collected_static")).resolve()

if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("SHIJIN_SECRET_KEY must be a strong private value.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("SHIJIN_ALLOWED_HOSTS must list exact hosts.")
if not CSRF_TRUSTED_ORIGINS or any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("SHIJIN_CSRF_TRUSTED_ORIGINS must list HTTPS origins.")
if DATA_DIR == STATIC_ROOT or DATA_DIR in STATIC_ROOT.parents or STATIC_ROOT in DATA_DIR.parents:
    raise ImproperlyConfigured("Data and static directories must be separate.")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 0  # Access is by IP; revisit only with a trusted hostname.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
