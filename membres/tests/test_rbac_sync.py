"""
Synchronisation RBAC & durcissements métier — points de rupture
====================================================================
Régressions corrigées lors de l'audit :
- les groupes n'étaient recalculés QUE sur sauvegarde d'un Mandat →
  membre créé sans mandat jamais `membre_actif`, changement de statut sans
  effet sur le groupe de base, et surtout soft-delete laissant des
  permissions fantômes (bureau conservé après suppression/restauration) ;
- matricules générés depuis le PK global → non séquentiels par chorale ;
- Chorale.is_active jamais appliqué (login, données, invitations) ;
- mots de passe non soumis aux validateurs Django.
"""

import pytest
from rest_framework.test import APIClient

from membres.models import Membre

pytestmark = pytest.mark.django_db


def _groupes(membre) -> set[str]:
    return set(membre.user.groups.values_list("name", flat=True))


# ---------------------------------------------------------------------------
# Resynchronisation des groupes
# ---------------------------------------------------------------------------

def test_membre_cree_sans_mandat_obtient_membre_actif(membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    assert "membre_actif" in _groupes(membre)


def test_changement_de_statut_change_le_groupe_de_base(membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    membre.statut = Membre.Statut.HONORAIRE
    membre.save()

    groupes = _groupes(membre)
    assert "membre_honoraire" in groupes
    assert "membre_actif" not in groupes


def test_soft_delete_retire_toutes_les_permissions(
    membre_factory, mandat_factory, chorale_a
):
    """Un membre bureau soft-deleted ne doit conserver AUCUN groupe."""
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "bureau")
    assert "bureau" in _groupes(membre)

    membre.soft_delete()

    assert _groupes(membre) == set()


def test_restore_ne_ressuscite_pas_les_permissions_de_mandat(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """
    Régression critique : après soft-delete + restore, le membre redevient
    actif (membre_actif) mais NE récupère PAS ses anciens droits bureau —
    ses mandats ont été clôturés, il faut les réattribuer explicitement.
    """
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    cible = membre_factory(chorale_a)
    mandat_factory(cible, "tresorier")

    cible.soft_delete()
    resp = auth_client(bureau).post(f"/api/membres/{cible.pk}/restore/")
    assert resp.status_code == 200

    groupes = _groupes(cible)
    assert "membre_actif" in groupes
    assert "tresorier" not in groupes


# ---------------------------------------------------------------------------
# Matricules séquentiels par chorale
# ---------------------------------------------------------------------------

def test_matricules_sequentiels_par_chorale(membre_factory, chorale_a, chorale_b):
    # Des membres dans A d'abord : leurs PK ne doivent pas influencer B.
    membre_factory(chorale_a)
    membre_factory(chorale_a)

    m1 = membre_factory(chorale_b)
    m2 = membre_factory(chorale_b)

    assert m1.numero_membre == "CHB-0001"
    assert m2.numero_membre == "CHB-0002"


# ---------------------------------------------------------------------------
# Suspension de chorale (is_active=False)
# ---------------------------------------------------------------------------

def test_login_refuse_pour_chorale_suspendue(membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    chorale_a.is_active = False
    chorale_a.save()

    resp = APIClient().post(
        "/api/auth/login/",
        {"username": membre.user.username, "password": "testpass123"},
        format="json",
    )
    assert resp.status_code == 401


def test_token_deja_emis_ne_voit_plus_rien_apres_suspension(
    auth_client, membre_factory, chorale_a
):
    """La suspension prend effet immédiatement, sans attendre l'expiration JWT."""
    from musique.models import Chant
    Chant.objects.create(chorale=chorale_a, titre="X", style="autre")
    membre = membre_factory(chorale_a)
    client = auth_client(membre)  # token émis AVANT la suspension

    chorale_a.is_active = False
    chorale_a.save()

    resp = client.get("/api/musique/chants/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0


def test_invitation_d_une_chorale_suspendue_invalide(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    code = auth_client(bureau).post("/api/membres/invitations/", {}, format="json").data["code"]

    chorale_a.is_active = False
    chorale_a.save()

    verif = APIClient().get(f"/api/membres/invitations/verifier/?code={code}")
    assert verif.data["valide"] is False


# ---------------------------------------------------------------------------
# Validateurs de mot de passe
# ---------------------------------------------------------------------------

def test_mot_de_passe_faible_refuse_a_la_creation_par_le_bureau(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")

    resp = auth_client(bureau).post(
        "/api/membres/",
        {
            "username": "faible", "password": "12345678",  # tout-numérique
            "first_name": "A", "last_name": "B", "statut": "actif",
            "date_adhesion": "2026-07-01",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "password" in resp.data


def test_mot_de_passe_faible_refuse_via_invitation(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    from django.core.cache import cache
    cache.clear()  # isole le throttle public
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    code = auth_client(bureau).post("/api/membres/invitations/", {}, format="json").data["code"]

    resp = APIClient().post(
        "/api/membres/invitations/rejoindre/",
        {
            "code": code, "username": "faible2", "password": "password",  # trop commun
            "first_name": "A", "last_name": "B",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "password" in resp.data
