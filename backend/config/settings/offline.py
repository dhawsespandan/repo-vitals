"""Settings for code that reads exported files and never a database.

The analysis notebooks (§10 Phase 14) import the product's own scoring engine
and the research harnesses — File C §1.1's "same pure functions the product
uses (exposed to the notebooks)" — and those modules import Django models, so
Django has to be configured. It does not have to be connected: every number a
notebook shows is computed from `research_data/exports/`, and a notebook that
quietly read a database would be reading something no replicator has.

So the database is Django's `dummy` backend, which raises on the first query.
That makes "the notebooks run from the exports alone" a property of the
configuration rather than a habit of whoever writes the next cell.
"""

import os

# Neither value is a secret: nothing here signs a cookie or decrypts a token.
os.environ.setdefault("DJANGO_SECRET_KEY", "offline-analysis-settings-not-a-secret")
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY", "b2ZmbGluZS1hbmFseXNpcy1ub3QtYS1zZWNyZXQhISE="
)
# `base` parses DATABASE_URL unconditionally; the value is replaced below.
os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")

from .base import *

DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
