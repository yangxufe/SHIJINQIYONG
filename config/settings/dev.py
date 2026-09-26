"""Loopback development with synthetic data only."""

from .base import *  # noqa: F403

SECRET_KEY = "development-only-not-for-lan-use"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SESSION_COOKIE_NAME = "xianchi_dev_session"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
