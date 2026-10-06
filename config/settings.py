import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "routeplanner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # route geometry compresses ~5x
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# No database is needed: stations are loaded once into memory from a CSV.
DATABASES = {}

USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache routes/geocodes in-process. Swap for Redis in production.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ---- Fuel planner configuration -------------------------------------------
FUEL_PLANNER = {
    "MAX_RANGE_MILES": 500,
    "MPG": 10,
    # Free routing API. The public OSRM demo server needs no key.
    # For production use your own OSRM instance or OpenRouteService.
    "OSRM_BASE_URL": os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org"),
    # Free geocoder, only used when start/finish are given as text (not "lat,lon").
    "NOMINATIM_URL": os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"),
    "USER_AGENT": os.environ.get("HTTP_USER_AGENT", "fuel-route-assessment/1.0 (contact: you@example.com)"),
    "HTTP_TIMEOUT_SECONDS": 15,
    # Stations are geocoded to city centroids, so allow a generous corridor.
    # The planner widens it step by step only if a leg is otherwise infeasible.
    "CORRIDOR_MILES_STEPS": [10, 25, 50],
    # Ignore stations that are cheaper by less than this ($/gal) -> fewer, more sensible stops.
    "MIN_PRICE_SAVING_PER_GALLON": 0.05,
    # Prefer hops of at least this many miles between stops (avoids top-up micro-stops).
    "MIN_LEG_MILES": 100,
    "CACHE_SECONDS": 3600,
}
