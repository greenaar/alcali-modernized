"""
Django settings for Alcali project.

"""
import os

# If there's our env var, it means that env file was loaded somehow(docker).
from os.path import join
from pathlib import Path
from dotenv import load_dotenv


def env_bool(name, default=False):
    """Read a boolean environment variable without the removed distutils module."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}

if not os.environ.get("DB_BACKEND"):
    # Load env file
    ENV_PATH = os.environ.get("ENV_PATH", os.getcwd())
    if not ENV_PATH:
        raise FileNotFoundError("ENV_PATH is not set")
    dotenv_path = join(ENV_PATH, ".env")
    env_file = Path(dotenv_path)
    if env_file.exists():
        load_dotenv(dotenv_path)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool("DJANGO_DEBUG")

# SECURITY WARNING: keep the secret key used in production secret!
# It also signs the JWTs, so a deployment that fell back to a key published in
# this repository would let anyone mint a valid token. Refuse to start instead.
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "SECRET_KEY is not set. Generate one and pass it in the environment; "
            "it signs session cookies and JWTs, so it must not be a shared default."
        )
    SECRET_KEY = "alcali-development-only-key"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "127.0.0.1").split(" ")

# Application definition

INSTALLED_APPS = [
    "api.apps.ApiConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_currentuser.middleware.ThreadLocalUserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "dist")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite3")
if DB_BACKEND == "sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DB_NAME", os.path.join(BASE_DIR, "alcali.sqlite3")),
            "ATOMIC_REQUESTS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": f"django.db.backends.{DB_BACKEND}",
            "ATOMIC_REQUESTS": True,
            "NAME": os.environ.get("DB_NAME"),
            "USER": os.environ.get("DB_USER"),
            "PASSWORD": os.environ.get("DB_PASS"),
            "HOST": os.environ.get("DB_HOST"),
            "PORT": os.environ.get("DB_PORT"),
        }
    }

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = "en-us"

USE_I18N = True

USE_TZ = env_bool("USE_TZ", default=False)

# Static files (CSS, JavaScript, Images)
# Place static in the same location as webpack build files
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "dist", "static")
STATICFILES_DIRS = []

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Secure reverse-proxy defaults. TLS verification for Salt itself is configured
# separately with SALT_VERIFY_TLS and SALT_CA_BUNDLE.
# Notification email. Unset EMAIL_HOST leaves Django on its console backend,
# which prints instead of sending - the right default for an installation that
# has not asked for mail, and harmless if a rule is configured before the
# server is.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS")
    EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL")
    EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "alcali@localhost")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE")
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split()
    if origin
]

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication"
    ],
}
# CORS_URLS_REGEX = r'^/api/.*$'
# CORS_ORIGIN_WHITELIST = [
#     "http://127.0.0.1:8001"
# ]

# SIMPLE_JWT = {
#     'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
#     'REFRESH_TOKEN_LIFETIME': timedelta(days=1)}

# Logging. stderr is kept by default because under systemd that is the journal,
# and in a container it is `docker logs`. LOG_FILE adds a file alongside it;
# LOG_CONSOLE=false then makes the file the only destination.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
LOG_FILE = os.environ.get("LOG_FILE", "").strip()
LOG_CONSOLE = env_bool("LOG_CONSOLE", default=True)


def _log_file_usable(path):
    """Can this process append to the log file?

    Checked up front because logging.config raises on a handler it cannot
    open, and that would take the whole site down over a log file - most often
    one a management command run as root left behind, owned by root.
    """
    try:
        with open(path, "a", encoding="utf-8"):
            return True
    except OSError as exc:
        import sys

        print(
            "alcali: cannot write LOG_FILE {}: {}; logging to stderr only".format(
                path, exc
            ),
            file=sys.stderr,
        )
        return False


_log_handlers = {}
if LOG_CONSOLE:
    _log_handlers["console"] = {
        "class": "logging.StreamHandler",
        "formatter": "console",
    }
if LOG_FILE and _log_file_usable(LOG_FILE):
    # Watched rather than rotating: gunicorn runs several worker processes,
    # and RotatingFileHandler in more than one process loses and interleaves
    # lines at rollover. This one reopens the file after logrotate moves it.
    _log_handlers["file"] = {
        "class": "logging.handlers.WatchedFileHandler",
        "filename": LOG_FILE,
        "formatter": "file",
    }
if not _log_handlers:
    # LOG_CONSOLE=false with no usable file would otherwise discard errors.
    _log_handlers["console"] = {
        "class": "logging.StreamHandler",
        "formatter": "console",
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # The journal already stamps the time and the pid.
        "console": {"format": "%(levelname)s %(name)s: %(message)s"},
        "file": {
            "format": "%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s"
        },
    },
    "handlers": _log_handlers,
    # Python warnings reach this through py.warnings (see ApiConfig.ready).
    "root": {"level": LOG_LEVEL, "handlers": list(_log_handlers)},
}

# Get version from file. A wheel install does not ship VERSION - it lands only
# in the sdist - so fall back to the installed distribution's own metadata.
try:
    with open(os.path.join(BASE_DIR, "VERSION"), "r") as fh:
        VERSION = fh.read().strip()
except FileNotFoundError:
    from importlib.metadata import PackageNotFoundError, version as _dist_version

    try:
        VERSION = _dist_version("alcali")
    except PackageNotFoundError:
        VERSION = "unknown"

# LDAP Authentication.
if os.environ.get("AUTH_BACKEND") and os.environ["AUTH_BACKEND"].lower() == "ldap":
    from .ldap_config import *

# Social Authentication.
if os.environ.get("AUTH_BACKEND") and os.environ["AUTH_BACKEND"].lower() == "social":
    INSTALLED_APPS += ["social_django", "rest_social_auth"]
    from .social_config import *
