"""
Configuration d'environnement — fermeture par défaut hors développement
========================================================================
Couvre `chm_config/env.py`, qui résout les réglages sensibles (clé secrète,
hôtes autorisés, CORS, base de données).

Règle vérifiée ici : **avec DJANGO_DEBUG=False, aucune configuration permissive
ne doit pouvoir résulter du simple oubli d'une variable d'environnement.**
Avant ce jalon, tous les défauts étaient ouverts (clé de dev versionnée,
ALLOWED_HOSTS=['*'], CORS ouvert à toute origine avec credentials) et aucun
n'était couplé à DJANGO_DEBUG.

Les fonctions testées sont pures : on leur passe un dictionnaire
d'environnement, sans toucher à `os.environ` ni recharger les settings.
"""

import os

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from chm_config import env as chm_env


# ---------------------------------------------------------------------------
# La suite PostgreSQL doit réellement frapper PostgreSQL (§9.2)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_la_suite_postgres_frappe_reellement_postgresql():
    """
    Garde-fou anti-faux-vert : si `DATABASE_URL` désigne PostgreSQL, la
    connexion de test doit être PostgreSQL. Sans cette vérification, une suite
    qui retomberait silencieusement sur SQLite passerait au vert sans jamais
    exercer les contraintes, verrous et types réels de la base cible.
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        pytest.skip("Suite locale SQLite : DATABASE_URL ne désigne pas PostgreSQL.")
    assert connection.vendor == "postgresql"


# ---------------------------------------------------------------------------
# SECRET_KEY
# ---------------------------------------------------------------------------

def test_secret_key_absente_hors_debug_refuse_de_demarrer():
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_secret_key({}, debug=False)


def test_secret_key_de_dev_explicite_refusee_hors_debug():
    """La clé de dev est versionnée : la fournir explicitement ne la rend pas sûre."""
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_secret_key({"DJANGO_SECRET_KEY": chm_env.CLE_DEV}, debug=False)


def test_secret_key_absente_en_debug_retombe_sur_la_cle_de_dev():
    assert chm_env.resoudre_secret_key({}, debug=True) == chm_env.CLE_DEV


def test_secret_key_fournie_est_utilisee():
    env = {"DJANGO_SECRET_KEY": "une-cle-propre-de-deploiement"}
    assert chm_env.resoudre_secret_key(env, debug=False) == "une-cle-propre-de-deploiement"


# ---------------------------------------------------------------------------
# ALLOWED_HOSTS
# ---------------------------------------------------------------------------

def test_allowed_hosts_absent_hors_debug_refuse_de_demarrer():
    """Plus de défaut `["*"]` : l'oubli est une erreur, pas une ouverture."""
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_allowed_hosts({}, debug=False)


def test_allowed_hosts_absent_en_debug_reste_local():
    hotes = chm_env.resoudre_allowed_hosts({}, debug=True)
    assert hotes == chm_env.HOTES_DEV
    assert "*" not in hotes


def test_allowed_hosts_liste_est_decoupee_et_nettoyee():
    env = {"DJANGO_ALLOWED_HOSTS": "localhost, 127.0.0.1 ,  , api.example.org"}
    assert chm_env.resoudre_allowed_hosts(env, debug=False) == [
        "localhost", "127.0.0.1", "api.example.org",
    ]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

def test_cors_ferme_par_defaut_hors_debug():
    cors = chm_env.resoudre_cors({}, debug=False)
    assert cors["allow_all_origins"] is False
    assert cors["allowed_origins"] == []


def test_cors_ouvert_par_defaut_en_debug():
    """Le confort de `ng serve` (4200) → API (8000) reste intact sur le poste de dev."""
    cors = chm_env.resoudre_cors({}, debug=True)
    assert cors["allow_all_origins"] is True


def test_cors_ouverture_globale_avec_credentials_refusee_hors_debug():
    """
    django-cors-headers ne renvoie pas `*` dans cette combinaison : il reflète
    l'origine de la requête en y ajoutant `Allow-Credentials: true`, donc
    autorise n'importe quel site tiers à appeler l'API avec les identifiants
    du navigateur.
    """
    env = {"CORS_ALLOW_ALL_ORIGINS": "True", "CORS_ALLOW_CREDENTIALS": "True"}
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_cors(env, debug=False)


def test_cors_origines_explicites_acceptees_hors_debug():
    env = {"CORS_ALLOWED_ORIGINS": "https://chorale.example.org"}
    cors = chm_env.resoudre_cors(env, debug=False)
    assert cors["allow_all_origins"] is False
    assert cors["allowed_origins"] == ["https://chorale.example.org"]


# ---------------------------------------------------------------------------
# Cookies sécurisés
# ---------------------------------------------------------------------------

def test_cookies_secure_par_defaut_hors_debug():
    assert chm_env.resoudre_cookies_secure({}, debug=False) is True


def test_cookies_secure_par_defaut_en_debug():
    """Django reste permissif par défaut sur le poste de dev (HTTP local)."""
    assert chm_env.resoudre_cookies_secure({}, debug=True) is True


def test_cookies_non_secure_refuses_hors_debug_sans_derogation():
    """
    Poser DJANGO_COOKIE_SECURE=False seul, hors DEBUG, ne suffit plus : un
    simple oubli de variable ne doit pas permettre d'obtenir des cookies non
    sécurisés.
    """
    env = {"DJANGO_COOKIE_SECURE": "False"}
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_cookies_secure(env, debug=False)


def test_cookies_non_secure_acceptes_hors_debug_avec_derogation_explicite():
    env = {
        "DJANGO_COOKIE_SECURE": "False",
        "DJANGO_ACCEPT_INSECURE_COOKIES": "True",
    }
    assert chm_env.resoudre_cookies_secure(env, debug=False) is False


def test_cookies_non_secure_refuses_meme_avec_derogation_mal_orthographiee():
    """La dérogation doit être exactement nommée : pas de tolérance implicite."""
    env = {
        "DJANGO_COOKIE_SECURE": "False",
        "DJANGO_ACCEPT_INSECURE_COOKIE": "True",  # faute : COOKIE, pas COOKIES
    }
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_cookies_secure(env, debug=False)


def test_cookies_non_secure_acceptes_sans_derogation_en_debug():
    """En dev, aucune dérogation à fournir : c'est le comportement historique."""
    env = {"DJANGO_COOKIE_SECURE": "False"}
    assert chm_env.resoudre_cookies_secure(env, debug=True) is False


# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------

def test_database_url_absente_hors_debug_ne_retombe_pas_sur_sqlite(tmp_path):
    """Aucun repli silencieux vers db.sqlite3 dans un conteneur."""
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_database({}, debug=False, base_dir=tmp_path)


def test_database_url_postgres_est_utilisee(tmp_path):
    env = {"DATABASE_URL": "postgresql://u:p@db:5432/choirmanager"}
    config = chm_env.resoudre_database(env, debug=False, base_dir=tmp_path)
    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "choirmanager"
    assert config["HOST"] == "db"
    assert config["CONN_HEALTH_CHECKS"] is True


def test_repli_sqlite_reste_possible_en_developpement(tmp_path):
    config = chm_env.resoudre_database({}, debug=True, base_dir=tmp_path)
    assert config["ENGINE"] == "django.db.backends.sqlite3"


def test_repli_sqlite_desactivable_explicitement_en_developpement(tmp_path):
    env = {"DJANGO_ALLOW_SQLITE": "False"}
    with pytest.raises(ImproperlyConfigured):
        chm_env.resoudre_database(env, debug=True, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Lecture brute
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("brut", ["True", "true", "1", "yes", "on", " TRUE "])
def test_env_bool_valeurs_vraies(brut):
    assert chm_env.env_bool({"X": brut}, "X", False) is True


@pytest.mark.parametrize("brut", ["False", "false", "0", "no", "off", "n'importe quoi"])
def test_env_bool_valeurs_fausses(brut):
    assert chm_env.env_bool({"X": brut}, "X", True) is False


def test_env_bool_variable_vide_vaut_non_renseignee():
    """Une variable posée à vide par Compose ne doit pas être lue comme False."""
    assert chm_env.env_bool({"X": "   "}, "X", True) is True
