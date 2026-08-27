"""Shared Django settings.

Environment-specific modules (`dev`, `prod`, `test`) import * from here and
override. Every configuration knob is registered in the plan's §6 registry;
`.env.example` is the executable copy of that table.
"""

from __future__ import annotations

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ── Core ───────────────────────────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# The single-page app's origin. Used for the OAuth landing redirect and as a
# CSRF trusted origin. All browser traffic reaches this backend through the
# Vercel rewrite (/api/* -> Render), so requests are same-site and one session
# cookie is enough — no CORS layer, no JWT machinery (§2).
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.github",
    # Local
    "apps.common",
    "apps.accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Required by django-allauth >= 0.56.
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

# ── Database ───────────────────────────────────────────────────────────────
# One URL, three contexts (D8): dev Docker Postgres, Supabase in prod, and the
# teammate's research Postgres for corpus/backfill commands.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"].setdefault("CONN_MAX_AGE", 60)
# Fail fast instead of hanging for the driver default: a background scan
# thread that cannot reach the database should mark its run failed within
# seconds, not tie up one of the eight worker threads. `connect_timeout` is a
# libpq option, so it is set only when the URL actually points at Postgres.
if "postgresql" in DATABASES["default"].get("ENGINE", ""):
    DATABASES["default"].setdefault("OPTIONS", {}).setdefault("connect_timeout", 10)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Identity ───────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# GitHub owns identity; RepoVitals owns the session. There are no passwords,
# no local signup form, and no email flows — allauth is used purely as the
# OAuth2 client (§2).
ACCOUNT_LOGIN_METHODS = {"username"}
ACCOUNT_SIGNUP_FIELDS: list[str] = []
ACCOUNT_USER_MODEL_USERNAME_FIELD = "github_username"
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "apps.accounts.adapters.RepoVitalsAccountAdapter"

SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.GitHubSocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_QUERY_EMAIL = True
# Skip allauth's interstitial "continue?" page: /api/auth/github/login/ is
# itself the user's deliberate click.
SOCIALACCOUNT_LOGIN_ON_GET = True
# D-list §11 "OAuth token exposure": allauth must never persist the access
# token in its own SocialToken table. The only copy lives Fernet-encrypted in
# app_users.encrypted_github_token.
SOCIALACCOUNT_STORE_TOKENS = False

SOCIALACCOUNT_PROVIDERS = {
    "github": {
        # `repo` is the narrowest scope GitHub OAuth Apps offer that can read
        # a private repository's tree. There is no read-only equivalent; the
        # enforced mitigation is that no backend code ever issues a write call
        # (grep-audited in Phase 9). A GitHub-App migration is out of scope
        # (§12).
        "SCOPE": ["repo", "read:user", "user:email"],
        "APPS": [
            {
                "provider_id": "github",
                "client_id": env("GITHUB_OAUTH_CLIENT_ID", default=""),
                "secret": env("GITHUB_OAUTH_CLIENT_SECRET", default=""),
                "key": "",
            }
        ],
        # allauth's documented override point (registry.py::ProviderRegistry.load)
        # for swapping in our provider subclass, which points the LOGIN step
        # at our adapter too — the callback-view adapter override in urls.py
        # only covers the callback step; see apps/accounts/oauth.py's
        # module docstring for why both are required (§1.14).
        "provider_class": "apps.accounts.oauth.RepoVitalsGitHubProvider",
    }
}

LOGIN_REDIRECT_URL = f"{FRONTEND_URL}/dashboard"
LOGIN_URL = f"{FRONTEND_URL}/login"

# Fernet key for app_users.encrypted_github_token. Rotating it invalidates
# every stored token — users simply re-login (§6).
TOKEN_ENCRYPTION_KEY = env("TOKEN_ENCRYPTION_KEY")

# ── Sessions, CSRF, cookies (§2) ───────────────────────────────────────────
SESSION_COOKIE_NAME = "repovitals_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_SAVE_EVERY_REQUEST = True

CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to echo the X-CSRFToken header
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]

# ── DRF ────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
    "UNAUTHENTICATED_USER": None,
}

# ── Static ─────────────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ── i18n ───────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Logging ────────────────────────────────────────────────────────────────
# Secrets are redacted by a filter rather than by discipline at call sites:
# the Phase 1 acceptance criterion is "no token substring in logs".
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_secrets": {"()": "apps.common.logging.RedactSecretsFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["redact_secrets"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": True},
    },
}
