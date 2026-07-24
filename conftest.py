"""
ChoirManager — Configuration pytest partagée
==============================================
Fixtures pour les tests de sécurité (isolation tenant + RBAC).

Objectif : fabriquer deux Chorale distinctes, des Membre avec des rôles
attribués via Mandat (comme en production — jamais via user.groups direct),
et un client API capable de s'authentifier par le vrai flux JWT.
"""

import random

import pytest
from django.contrib.auth.models import Group, User
from django.db import transaction
from rest_framework.test import APIClient

from core.models import Chorale
from finances.models import CategorieMouvement, Mouvement
from membres.models import Mandat, Membre, Poste

# Groupes RBAC utilisés par les tests (doivent exister AVANT tout Mandat :
# le signal sync_groupes_membre ne pose un groupe que s'il existe déjà).
GROUPES_RBAC = ["membre_actif", "membre_honoraire", "bureau", "tresorier", "maitre_choeur"]

# Pool de rôles tirés au sort pour les membres « génériques » d'une chorale.
ROLES_ALEATOIRES = ["bureau", "tresorier", "maitre_choeur", None]


# ---------------------------------------------------------------------------
# Groupes
# ---------------------------------------------------------------------------

@pytest.fixture
def groupes(db):
    """Crée les groupes Django du RBAC."""
    return {nom: Group.objects.get_or_create(name=nom)[0] for nom in GROUPES_RBAC}


# ---------------------------------------------------------------------------
# Chorales
# ---------------------------------------------------------------------------

@pytest.fixture
def chorale_a(db):
    return Chorale.objects.create(
        nom="Chorale A", prefix="CHA", date_creation="2020-01-01"
    )


@pytest.fixture
def chorale_b(db):
    return Chorale.objects.create(
        nom="Chorale B", prefix="CHB", date_creation="2020-01-01"
    )


# ---------------------------------------------------------------------------
# Factories Membre / Mandat
# ---------------------------------------------------------------------------

@pytest.fixture
def membre_factory(db):
    """
    Fabrique un Membre (+ User) dans une chorale donnée.
    Le mot de passe est fixé pour permettre le login JWT dans les tests.
    """
    compteur = {"n": 0}

    def _make(chorale, statut=Membre.Statut.ACTIF, password="testpass123", sexe=None):
        compteur["n"] += 1
        username = f"user{compteur['n']}_{chorale.prefix.lower()}"
        # `generer_numero` verrouille la ligne Chorale et exige donc un bloc
        # atomique englobant la création du membre (cf. Membre.generer_numero).
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                email=f"{username}@example.com",
                first_name="Prenom",
                last_name=f"Nom{compteur['n']}",
            )
            membre = Membre.objects.create(
                user=user,
                chorale=chorale,
                numero_membre=Membre.generer_numero(chorale),
                date_adhesion="2021-01-01",
                statut=statut,
                # Alterné plutôt que vide : le sexe conditionne les tarifs de
                # cotisation par genre, un jeu de test tout-vide ne les
                # exercerait jamais. Surchargeable par test.
                sexe=sexe if sexe is not None else (
                    Membre.Sexe.FEMME if compteur["n"] % 2 else Membre.Sexe.HOMME
                ),
                telephone=f"+228 90 00 {compteur['n']:02d} {compteur['n']:02d}",
            )
        membre._password = password  # pratique pour le login dans les tests
        return membre

    return _make


@pytest.fixture
def mandat_factory(db, groupes):
    """
    Attribue un rôle à un membre via un Poste (lié au groupe Django
    correspondant) + un Mandat actif. C'est le seul chemin légitime
    d'attribution de permission — le signal synchronise user.groups.
    """
    def _make(membre, role, is_active=True):
        poste, _ = Poste.objects.get_or_create(
            chorale=membre.chorale,
            nom=f"Poste {role}",
            defaults={"type_poste": Poste.TypePoste.BUREAU, "unique_actif": False},
        )
        if role in groupes:
            poste.groupes.add(groupes[role])
        return Mandat.objects.create(
            membre=membre,
            poste=poste,
            date_debut="2021-01-01",
            is_active=is_active,
        )

    return _make


# ---------------------------------------------------------------------------
# Deux chorales peuplées de 3 membres à rôles aléatoires
# ---------------------------------------------------------------------------

@pytest.fixture
def chorales_peuplees(membre_factory, mandat_factory, chorale_a, chorale_b):
    """
    Deux chorales distinctes, chacune avec 3 membres dont les rôles sont
    tirés au sort (bureau / trésorier / maître de chœur / aucun).
    Renvoie {'a': (chorale, [membres]), 'b': (chorale, [membres])}.
    """
    resultat = {}
    for cle, chorale in (("a", chorale_a), ("b", chorale_b)):
        membres = []
        for _ in range(3):
            membre = membre_factory(chorale)
            role = random.choice(ROLES_ALEATOIRES)
            if role:
                mandat_factory(membre, role)
            membres.append(membre)
        resultat[cle] = (chorale, membres)
    return resultat


# ---------------------------------------------------------------------------
# Ressource finances par chorale (pour les tests d'isolation)
# ---------------------------------------------------------------------------

@pytest.fixture
def mouvement_factory(db, membre_factory):
    """Crée un mouvement financier appartenant à une chorale donnée."""
    def _make(chorale, enregistre_par=None):
        if enregistre_par is None:
            enregistre_par = membre_factory(chorale)
        categorie, _ = CategorieMouvement.objects.get_or_create(
            chorale=chorale,
            nom="Divers",
            defaults={"type_mouvement": "entree"},
        )
        return Mouvement.objects.create(
            chorale=chorale,
            date="2025-01-15",
            montant="1000.00",
            sens=Mouvement.Sens.ENTREE,
            categorie=categorie,
            motif="Don anonyme",
            enregistre_par=enregistre_par,
        )

    return _make


# ---------------------------------------------------------------------------
# Client API authentifié via le vrai flux JWT
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(db):
    """
    Factory : renvoie un APIClient authentifié pour le membre donné,
    via le VRAI endpoint /api/auth/login/ (fidèle à la production JWT).
    """
    def _login(membre, password="testpass123"):
        client = APIClient()
        resp = client.post(
            "/api/auth/login/",
            {"username": membre.user.username, "password": password},
            format="json",
        )
        assert resp.status_code == 200, f"Login échoué: {resp.status_code} {resp.content}"
        token = resp.data["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    return _login
