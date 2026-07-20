from pathlib import Path
import os
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent

load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env.local", override=True)
load_dotenv(PROJECT_DIR / ".env.development.local", override=True)

DEFAULT_RUNTIME_DIR = Path("/tmp/ClinicaEspiro") if os.getenv("VERCEL") else Path.home() / "AppData" / "Local" / "ClinicaEspiro"
RUNTIME_DIR = Path(os.getenv("APP_RUNTIME_DIR", DEFAULT_RUNTIME_DIR))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def env_value(name, default=""):
    return os.getenv(name, default).strip()


def sqlite_database_config():
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": RUNTIME_DIR / "dev.sqlite3",
    }


def postgres_url_config(database_url):
    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/") or env_value("DB_NAME", "postgres"),
        "USER": parsed.username or env_value("DB_USER"),
        "PASSWORD": parsed.password or env_value("DB_PASSWORD"),
        "HOST": parsed.hostname or env_value("DB_HOST", "127.0.0.1"),
        "PORT": str(parsed.port or env_value("DB_PORT", "5432")),
        "OPTIONS": {
            "sslmode": query.get("sslmode", [env_value("DB_SSLMODE", "require")])[0],
        },
    }


def build_database_config():
    if env_value("FORCE_LOCAL_QA", "False").lower() == "true":
        return sqlite_database_config()
    database_url = env_value("DATABASE_URL") or env_value("POSTGRES_URL") or env_value("POSTGRES_URL_NON_POOLING")
    if database_url:
        return postgres_url_config(database_url)

    db_name = env_value("DB_NAME") or env_value("POSTGRES_DATABASE")
    db_user = env_value("DB_USER") or env_value("POSTGRES_USER")
    db_password = env_value("DB_PASSWORD") or env_value("POSTGRES_PASSWORD")
    db_host = env_value("DB_HOST") or env_value("POSTGRES_HOST")

    if any([db_name, db_user, db_password, db_host]):
        missing = [
            name
            for name, value in {
                "DB_NAME/POSTGRES_DATABASE": db_name,
                "DB_USER/POSTGRES_USER": db_user,
                "DB_PASSWORD/POSTGRES_PASSWORD": db_password,
                "DB_HOST/POSTGRES_HOST": db_host,
            }.items()
            if not value
        ]
        if missing:
            if env_value("REQUIRE_DATABASE", "False").lower() == "true":
                raise ImproperlyConfigured(
                    "PostgreSQL environment variables are incomplete. "
                    f"Missing: {', '.join(missing)}. "
                    "For Supabase, set DATABASE_URL to the IPv4-compatible Session Pooler connection string."
                )
            return sqlite_database_config()

        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_name,
            "USER": db_user,
            "PASSWORD": db_password,
            "HOST": db_host,
            "PORT": env_value("DB_PORT", "5432"),
            "OPTIONS": {
                "sslmode": env_value("DB_SSLMODE", "require"),
            },
        }

    return sqlite_database_config()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
IS_PRODUCTION = os.getenv("VERCEL", "").lower() in {"1", "true"} or os.getenv(
    "APP_ENV", ""
).lower() == "production"
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",") if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "clinic",
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
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PROJECT_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "clinic.context_processors.current_work_mode",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": build_database_config()}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [PROJECT_DIR / "static"] if (PROJECT_DIR / "static").exists() else []
STATIC_ROOT = RUNTIME_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = RUNTIME_DIR / "media"
SUPABASE_URL = env_value("SUPABASE_URL")
SUPABASE_STORAGE_API_KEY = env_value("SUPABASE_SECRET_KEY") or env_value("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = env_value("SUPABASE_STORAGE_BUCKET", "attachments")
SUPABASE_STORAGE_SIGNED_URL_TTL = int(env_value("SUPABASE_STORAGE_SIGNED_URL_TTL", "3600") or "3600")
USE_SUPABASE_STORAGE = (
    env_value("FORCE_LOCAL_QA", "False").lower() != "true"
    and env_value("USE_SUPABASE_STORAGE", "True").lower() == "true"
    and bool(SUPABASE_URL)
    and bool(SUPABASE_STORAGE_API_KEY)
)

if USE_SUPABASE_STORAGE:
    STORAGES = {
        "default": {"BACKEND": "config.storage.SupabaseStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }

# The Vercel Python function bundles the source tree; finders let WhiteNoise
# serve project and Django admin assets without relying on an ephemeral build directory.
WHITENOISE_USE_FINDERS = True

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", str(IS_PRODUCTION)).lower() == "true"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", str(IS_PRODUCTION)).lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", str(IS_PRODUCTION)).lower() == "true"
SECURE_HSTS_SECONDS = int(env_value("SECURE_HSTS_SECONDS", "3600" if IS_PRODUCTION else "0") or "0")
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
AUTO_PURGE_RECYCLE_BIN = os.getenv("AUTO_PURGE_RECYCLE_BIN", "False").lower() == "true"

if IS_PRODUCTION and (DEBUG or SECRET_KEY == "dev-secret-key-change-me"):
    raise RuntimeError("Produccion requiere DEBUG=False y un SECRET_KEY seguro.")

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "clinic:dashboard"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
