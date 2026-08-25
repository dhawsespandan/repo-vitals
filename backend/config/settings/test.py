"""Test settings. Never reads a .env file — CI supplies everything."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-used-anywhere")
os.environ.setdefault(
    "DATABASE_URL", "postgres://repovitals:repovitals@localhost:5432/repovitals"
)
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
# A fixed, obviously-fake Fernet key so encryption round-trips are
# reproducible across machines and CI runs.
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY", "cmVwb3ZpdGFscy10ZXN0LWtleS1kby1ub3QtdXNlISE="
)

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["*"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# WhiteNoise serves collected static files; nothing is collected in a test run,
# and its "no such directory" warning is pure noise on every test.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
