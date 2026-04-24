"""Base settings shared by development and production."""
import os
import sys
from pathlib import Path

import environ

# backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# repo root (one level above backend/)
REPO_ROOT = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    env.read_env(str(env_file))

# GeoDjango on Windows: PostgreSQL's PostGIS installer ships libgdal-35.dll and
# libgeos_c.dll in C:\Program Files\PostgreSQL\15\bin but Django searches for
# gdal30x/geos_c by default. Point it at absolute paths via env and register the
# directory so transitive DLLs (libproj, libsqlite3, etc.) resolve too.
GDAL_LIBRARY_PATH = env.str("GDAL_LIBRARY_PATH", default="")
GEOS_LIBRARY_PATH = env.str("GEOS_LIBRARY_PATH", default="")
if sys.platform == "win32":
    for _path in (GDAL_LIBRARY_PATH, GEOS_LIBRARY_PATH):
        _dir = os.path.dirname(_path) if _path else ""
        if _dir and os.path.isdir(_dir):
            os.add_dll_directory(_dir)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # 3rd party
    "rest_framework",
    "rest_framework_gis",
    "django_filters",
    "corsheaders",
    "django_extensions",
    "django_celery_beat",
    # local
    "apps.core",
    "apps.gtfs",
    "apps.realtime",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
# Force PostGIS backend regardless of what env.db() inferred
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework_gis.filters.InBBoxFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# Redis — shared across Celery (broker/result), rate limiter, distributed
# lock, mapping cache, and pub/sub. Single URL, single source of truth.
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

# Celery — worker/beat config. Tasks populated in Phase 2 Step 2+.
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {}
