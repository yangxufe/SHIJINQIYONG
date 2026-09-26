"""Isolated test settings; the runner creates its own database."""

from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret-not-for-deployment"
ALLOWED_HOSTS = ["testserver", "127.0.0.1"]
DATABASES["default"]["NAME"] = BASE_DIR / "work" / "test.sqlite3"
DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / "work" / "test_file.sqlite3"}
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
