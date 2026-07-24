"""
ChoirManager — Configuration Django
====================================
Settings principal du projet. PostgreSQL via `DATABASE_URL` ; repli SQLite
explicite réservé au poste de développement.

Les réglages sensibles (clé secrète, hôtes autorisés, CORS, base de données)
sont résolus par `chm_config/env.py` : le défaut y est **fermé** dès que
`DJANGO_DEBUG=False`, de sorte qu'aucune configuration permissive ne puisse
résulter du simple oubli d'une variable d'environnement.
"""

import os
from datetime import timedelta
from pathlib import Path

from chm_config import env as chm_env

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security — cf. chm_config/env.py pour les règles de fermeture par défaut
# ---------------------------------------------------------------------------
DEBUG = chm_env.resoudre_debug(os.environ)

SECRET_KEY = chm_env.resoudre_secret_key(os.environ, DEBUG)

ALLOWED_HOSTS = chm_env.resoudre_allowed_hosts(os.environ, DEBUG)

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Tiers
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",

    # ChoirManager
    "core.apps.CoreConfig",
    "authentication.apps.AuthenticationConfig",
    "membres.apps.MembresConfig",
    "musique.apps.MusiqueConfig",
    "presences.apps.PresencesConfig",
    "finances.apps.FinancesConfig",
    "communications.apps.CommunicationsConfig",
    "rapports.apps.RapportsConfig",
    "notifications.apps.NotificationsConfig",
]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sert les statiques de l'admin Django depuis le conteneur, sans dépendre
    # d'un serveur de fichiers externe (le front a son propre Nginx).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.ChoraleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "chm_config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "chm_config.wsgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL via DATABASE_URL
# ---------------------------------------------------------------------------
# `DATABASE_URL` fait autorité (Compose et CI la fournissent toujours). Le repli
# SQLite subsiste pour le poste de développement mais reste explicite : il exige
# DJANGO_DEBUG=True. Dans un conteneur, une DATABASE_URL absente est une erreur
# de démarrage — jamais un repli silencieux sur db.sqlite3.
DATABASES = {
    "default": chm_env.resoudre_database(os.environ, DEBUG, BASE_DIR),
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Lome"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # WhiteNoise compresse et empreinte les statiques collectés. Variante non
    # « manifest » en DEBUG : le manifeste exige un collectstatic préalable,
    # ce qui casserait `runserver` sur un poste fraîchement cloné.
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "DATE_FORMAT": "%Y-%m-%d",
    # Taux anti-abus des endpoints publics (non authentifiés) — cf. core/throttles.py.
    # Pas de DEFAULT_THROTTLE_CLASSES global : chaque vue publique déclare
    # explicitement son throttle_classes/throttle_scope pour rester lisible.
    "DEFAULT_THROTTLE_RATES": {
        "demande_chorale": "5/day",
        "invitation_verifier": "20/hour",
        "invitation_rejoindre": "10/hour",
    },
}

# En mode DEBUG, ajouter le BrowsableAPI pour faciliter le développement
if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
        "rest_framework.renderers.BrowsableAPIRenderer"
    )

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    # 30 min (et non 2 h) : le front décode les rôles depuis l'access token —
    # après un changement de mandat ou une révocation, l'UI reste périmée
    # jusqu'à son expiration. Le refresh silencieux (intercepteur Angular)
    # ré-embarque alors les groupes frais : l'obsolescence s'auto-guérit vite.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "authentication.serializers.CustomTokenObtainPairSerializer",
}

# ---------------------------------------------------------------------------
# Email — notifications (best-effort, cf. notifications/services.py)
# ---------------------------------------------------------------------------
# Dev : backend console (les mails s'affichent dans le terminal du runserver).
# Prod : définir EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# et les EMAIL_HOST* ci-dessous via variables d'environnement.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "ChoirManager <no-reply@choirmanager.local>")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# En développement : ouvert, pour que `ng serve` (4200) atteigne l'API (8000).
# Hors développement : fermé par défaut — l'ouverture passe obligatoirement par
# CORS_ALLOWED_ORIGINS. La cible de production est same-origin (Nginx sert le
# front et relaie /api/ vers le backend), donc sans CORS du tout.
_cors = chm_env.resoudre_cors(os.environ, DEBUG)
CORS_ALLOW_ALL_ORIGINS = _cors["allow_all_origins"]
CORS_ALLOWED_ORIGINS = _cors["allowed_origins"]
CORS_ALLOW_CREDENTIALS = _cors["allow_credentials"]

# ---------------------------------------------------------------------------
# Réglages de sécurité appliqués hors développement
# ---------------------------------------------------------------------------
# Actifs seulement quand DJANGO_DEBUG=False, pour ne pas casser le HTTP local.
# `DJANGO_SECURE_SSL_REDIRECT` reste débrayable : derrière un reverse-proxy qui
# termine déjà TLS, la redirection appartient au proxy, pas à Django.
if not DEBUG:
    SECURE_SSL_REDIRECT = chm_env.env_bool(os.environ, "DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Cookies `Secure` par défaut (posture fermée). Un navigateur ne renvoie
    # JAMAIS un cookie `Secure` sur une connexion HTTP : sur une pile locale
    # servie en clair, laisser True rend la connexion à l'admin Django
    # impossible (le cookie CSRF n'est jamais retourné → 403). D'où ce
    # débrayage explicite, réservé aux environnements sans TLS.
    _cookies_secure = chm_env.env_bool(os.environ, "DJANGO_COOKIE_SECURE", True)
    SESSION_COOKIE_SECURE = _cookies_secure
    CSRF_COOKIE_SECURE = _cookies_secure
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    CSRF_TRUSTED_ORIGINS = chm_env.env_list(os.environ, "DJANGO_CSRF_TRUSTED_ORIGINS")
