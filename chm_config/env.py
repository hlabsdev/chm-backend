"""
ChoirManager — Résolution des réglages sensibles depuis l'environnement
=======================================================================

Ces fonctions sont volontairement **pures** : elles reçoivent le mapping
d'environnement en argument plutôt que de lire `os.environ` directement. Elles
sont donc testables sans recharger `chm_config.settings` (un `importlib.reload`
sur le module de settings muterait l'objet qu'enveloppe `django.conf.settings`).

Règle du jalon PostgreSQL/Docker : **le défaut est fermé, l'ouverture est
explicite.**

Tant que `DJANGO_DEBUG=True` (poste de développement), les valeurs de confort
historiques restent en place — `runserver` et le front Angular local continuent
de fonctionner sans aucune variable. Dès que `DJANGO_DEBUG=False`, plus aucun
réglage permissif ne peut être obtenu par **simple oubli** d'une variable :
soit elle est fournie explicitement, soit le démarrage échoue franchement.

Avant ce jalon, tous les défauts étaient ouverts et aucun n'était couplé à
`DJANGO_DEBUG` : un déploiement posant seulement `DJANGO_DEBUG=False` héritait
de la clé secrète versionnée, de `ALLOWED_HOSTS=['*']` et d'un CORS reflétant
n'importe quelle origine avec `Allow-Credentials: true`.
"""

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Représentations acceptées pour un booléen d'environnement.
VALEURS_VRAIES = ("true", "1", "yes", "on")

# Clé de développement historique — versionnée, donc publiquement connue.
# Elle ne doit jamais servir hors DEBUG, même si elle est passée explicitement.
CLE_DEV = "dev-insecure-key-change-in-production-!@#$%^&*()"

# Valeurs de confort appliquées uniquement en développement.
HOTES_DEV = ["localhost", "127.0.0.1", "[::1]"]
ORIGINES_DEV = ["http://localhost:4200", "http://127.0.0.1:4200"]


# ---------------------------------------------------------------------------
# Lecture brute
# ---------------------------------------------------------------------------

def env_bool(env, nom, defaut):
    """Booléen d'environnement ; une variable vide vaut « non renseignée »."""
    brut = env.get(nom)
    if brut is None or not brut.strip():
        return defaut
    return brut.strip().lower() in VALEURS_VRAIES


def env_list(env, nom):
    """Liste séparée par des virgules, vidée de ses entrées blanches."""
    return [v.strip() for v in env.get(nom, "").split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Réglages sensibles
# ---------------------------------------------------------------------------

def resoudre_debug(env):
    """`DJANGO_DEBUG` reste le pivot : il distingue le poste de dev du reste."""
    return env_bool(env, "DJANGO_DEBUG", True)


def resoudre_secret_key(env, debug):
    cle = env.get("DJANGO_SECRET_KEY", "").strip()
    if not cle:
        if debug:
            return CLE_DEV
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY est obligatoire lorsque DJANGO_DEBUG=False. "
            "Aucune clé de développement n'est utilisée hors développement."
        )
    if not debug and cle == CLE_DEV:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY reprend la clé de développement versionnée "
            "(donc publiquement connue). Générer une clé dédiée pour tout "
            "déploiement DJANGO_DEBUG=False."
        )
    return cle


def resoudre_allowed_hosts(env, debug):
    """
    Plus de défaut `["*"]`. En dev on retombe sur les hôtes locaux ; hors dev
    la variable est obligatoire. Une valeur `*` explicite reste honorée : c'est
    un choix délibéré (reverse-proxy de confiance), pas un oubli.
    """
    hotes = env_list(env, "DJANGO_ALLOWED_HOSTS")
    if hotes:
        return hotes
    if debug:
        return list(HOTES_DEV)
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS est obligatoire lorsque DJANGO_DEBUG=False "
        "(ex. « localhost,127.0.0.1 » ou le domaine public servi)."
    )


def resoudre_cors(env, debug):
    """
    Retourne le triplet CORS. Le défaut de `CORS_ALLOW_ALL_ORIGINS` suit
    `DEBUG` : ouvert sur le poste de dev, fermé partout ailleurs.

    L'ouverture globale **avec** credentials est refusée hors dev : dans cette
    combinaison django-cors-headers ne renvoie pas `*` mais reflète l'origine
    de la requête en y ajoutant `Access-Control-Allow-Credentials: true`,
    c'est-à-dire autorise n'importe quel site tiers à appeler l'API avec les
    identifiants du navigateur. La cible de production est de toute façon
    same-origin (Nginx sert le front et relaie `/api/`), donc sans CORS.
    """
    tout_ouvert = env_bool(env, "CORS_ALLOW_ALL_ORIGINS", debug)
    credentials = env_bool(env, "CORS_ALLOW_CREDENTIALS", True)
    origines = env_list(env, "CORS_ALLOWED_ORIGINS")
    if not origines and debug:
        origines = list(ORIGINES_DEV)

    if not debug and tout_ouvert and credentials:
        raise ImproperlyConfigured(
            "CORS_ALLOW_ALL_ORIGINS=True combiné à CORS_ALLOW_CREDENTIALS=True "
            "est refusé lorsque DJANGO_DEBUG=False : cela autorise n'importe "
            "quelle origine à appeler l'API avec les identifiants du "
            "navigateur. Renseigner CORS_ALLOWED_ORIGINS à la place."
        )

    return {
        "allow_all_origins": tout_ouvert,
        "allowed_origins": origines,
        "allow_credentials": credentials,
    }


def resoudre_database(env, debug, base_dir):
    """
    `DATABASE_URL` fait autorité. Le repli SQLite existe encore pour le poste de
    développement mais il est **explicite** : il exige DJANGO_DEBUG=True et
    n'est jamais silencieux. Dans un conteneur (DJANGO_DEBUG=False) l'absence
    de DATABASE_URL est une erreur de démarrage, pas un repli sur db.sqlite3.
    """
    url = env.get("DATABASE_URL", "").strip()
    if url:
        return dj_database_url.parse(
            url,
            conn_max_age=60,
            conn_health_checks=True,
        )

    if debug and env_bool(env, "DJANGO_ALLOW_SQLITE", True):
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "db.sqlite3",
        }

    raise ImproperlyConfigured(
        "DATABASE_URL est obligatoire : aucun repli silencieux vers db.sqlite3 "
        "hors développement (DJANGO_DEBUG=True et DJANGO_ALLOW_SQLITE≠False)."
    )
