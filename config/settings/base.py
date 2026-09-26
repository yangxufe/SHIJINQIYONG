"""Shared settings for the single-household application."""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SHIJIN_DATA_DIR", BASE_DIR / "data")).resolve()

SECRET_KEY = os.environ.get("SHIJIN_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "core",
    "inventory",
    "meals",
    "shopping",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.ResponsePolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.AuthenticationGateMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
AXES_CLIENT_IP_CALLABLE = "core.security.axes_client_ip"
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_USE_ATTEMPT_EXPIRATION = True
AXES_LOCKOUT_TEMPLATE = "core/locked.html"
AXES_HTTP_RESPONSE_CODE = 429
AXES_RESET_ON_SUCCESS = False

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "index"

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "app.sqlite3",
        "OPTIONS": {"timeout": 2, "transaction_mode": "IMMEDIATE"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = os.environ.get("SHIJIN_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "collected_static"
STATICFILES_DIRS = [BASE_DIR / "static"]
DATA_UPLOAD_MAX_MEMORY_SIZE = 4_194_304  # Non-file form fields; Caddy keeps ordinary routes at 64 KiB.
DATA_UPLOAD_MAX_NUMBER_FILES = 2  # Recipe upload uses one file; reject abusive multipart requests early.
FILE_UPLOAD_MAX_MEMORY_SIZE = 65_536
FILE_UPLOAD_TEMP_DIR = DATA_DIR  # Large multipart files stay under the private data ACL.

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_NAME = "__Host-xianchi_session"
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "core.views.csrf_failure"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Only Caddy on loopback may supply these headers; Waitress enforces that peer.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
