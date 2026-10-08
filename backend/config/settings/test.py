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

# The suite's hand-worked scores (test_scan_scoring, test_rescore, the
# validation fixtures) are computed under v1's round numbers, so the suite pins
# v1 rather than following the shipped default. The default itself is v2,
# asserted in test_weights_loader against `config.settings.base`.
WEIGHTS_VERSION = "v1"

# WhiteNoise serves collected static files; nothing is collected in a test run,
# and its "no such directory" warning is pure noise on every test.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
