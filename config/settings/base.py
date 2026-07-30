import os
from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env")


SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env.bool("DJANGO_DEBUG")

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts.apps.AccountsConfig",
    "apps.wholesale.apps.WholesaleConfig",
    "apps.locations.apps.LocationsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.prescriptions.apps.PrescriptionsConfig",
    "apps.lenses.apps.LensesConfig",
    "apps.wholesale_catalog.apps.WholesaleCatalogConfig",
    "apps.wholesale_cart.apps.WholesaleCartConfig",
    "apps.wholesale_orders.apps.WholesaleOrdersConfig",
    "apps.retail_cart.apps.RetailCartConfig",
    "apps.retail_orders.apps.RetailOrdersConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


AUTH_USER_MODEL = "accounts.User"


LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"

USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


WHOLESALE_LOGIN_URL = "/wholesale/login/"

# Phone OTP authentication
PHONE_OTP_PROVIDER = env(
    "PHONE_OTP_PROVIDER",
    default=(
        "apps.accounts.otp.providers.console."
        "ConsoleOTPProvider"
    ),
)
PHONE_OTP_CODE_LENGTH = env.int(
    "PHONE_OTP_CODE_LENGTH",
    default=6,
)
PHONE_OTP_TTL_SECONDS = env.int(
    "PHONE_OTP_TTL_SECONDS",
    default=300,
)
PHONE_OTP_RESEND_SECONDS = env.int(
    "PHONE_OTP_RESEND_SECONDS",
    default=60,
)
PHONE_OTP_MAX_ATTEMPTS = env.int(
    "PHONE_OTP_MAX_ATTEMPTS",
    default=5,
)
PHONE_OTP_MAX_SENDS_PER_HOUR = env.int(
    "PHONE_OTP_MAX_SENDS_PER_HOUR",
    default=5,
)



# Razorpay payment gateway
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get(
    "RAZORPAY_WEBHOOK_SECRET",
    "",
)
RAZORPAY_API_BASE_URL = os.environ.get(
    "RAZORPAY_API_BASE_URL",
    "https://api.razorpay.com/v1",
)
RAZORPAY_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("RAZORPAY_REQUEST_TIMEOUT_SECONDS", "15")
)


# Retail notification delivery
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Chokher Alo <no-reply@localhost>",
)

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

RETAIL_NOTIFICATION_EMAIL_BACKEND = os.environ.get(
    "RETAIL_NOTIFICATION_EMAIL_BACKEND",
    (
        "apps.retail_orders.notifications."
        "DjangoEmailNotificationBackend"
    ),
)

RETAIL_NOTIFICATION_SMS_BACKEND = os.environ.get(
    "RETAIL_NOTIFICATION_SMS_BACKEND",
    (
        "apps.retail_orders.notifications."
        "DevelopmentSMSNotificationBackend"
    ),
)

RETAIL_NOTIFICATION_MAX_ATTEMPTS = int(
    os.environ.get(
        "RETAIL_NOTIFICATION_MAX_ATTEMPTS",
        "5",
    )
)

RETAIL_NOTIFICATION_BATCH_SIZE = int(
    os.environ.get(
        "RETAIL_NOTIFICATION_BATCH_SIZE",
        "100",
    )
)
