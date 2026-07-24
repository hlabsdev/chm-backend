"""
Invitations choriste — génération (Bureau) + auto-inscription publique
===========================================================================
Remplace l'ancienne auto-inscription ouverte (retirée pour faille de
sécurité). Ici, rejoindre une chorale exige un code long et aléatoire,
généré volontairement par le Bureau — jamais une inscription "à l'aveugle".
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from membres.models import InvitationChorale, Membre

pytestmark = pytest.mark.django_db

URL_LISTE = "/api/membres/invitations/"
URL_VERIFIER = "/api/membres/invitations/verifier/"
URL_REJOINDRE = "/api/membres/invitations/rejoindre/"


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def bureau_a(membre_factory, mandat_factory, chorale_a):
    m = membre_factory(chorale_a)
    mandat_factory(m, "bureau")
    return m


# ---------------------------------------------------------------------------
# Gestion Bureau
# ---------------------------------------------------------------------------

def test_bureau_cree_un_code_invitation(auth_client, bureau_a, chorale_a):
    resp = auth_client(bureau_a).post(URL_LISTE, {"note": "Recrutement Pâques"}, format="json")
    assert resp.status_code == 201, resp.data
    assert len(resp.data["code"]) == 8
    assert resp.data["est_valide"] is True

    invitation = InvitationChorale.objects.get(code=resp.data["code"])
    assert invitation.chorale_id == chorale_a.id
    assert invitation.cree_par_id == bureau_a.id


def test_membre_simple_ne_peut_pas_creer_de_code(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    resp = auth_client(membre).post(URL_LISTE, {}, format="json")
    assert resp.status_code == 403


def test_isolation_tenant_liste_invitations(
    auth_client, bureau_a, chorale_a, chorale_b, membre_factory, mandat_factory
):
    bureau_b = membre_factory(chorale_b)
    mandat_factory(bureau_b, "bureau")
    auth_client(bureau_b).post(URL_LISTE, {}, format="json")
    auth_client(bureau_a).post(URL_LISTE, {}, format="json")

    liste = auth_client(bureau_a).get(URL_LISTE)
    assert liste.data["count"] == 1


# ---------------------------------------------------------------------------
# Vérification publique
# ---------------------------------------------------------------------------

def test_verifier_code_valide(auth_client, bureau_a, chorale_a):
    code = auth_client(bureau_a).post(URL_LISTE, {}, format="json").data["code"]

    resp = APIClient().get(f"{URL_VERIFIER}?code={code}")
    assert resp.status_code == 200
    assert resp.data["valide"] is True
    assert resp.data["chorale_nom"] == chorale_a.nom


def test_verifier_code_inconnu_renvoie_invalide_sans_erreur(auth_client, bureau_a):
    resp = APIClient().get(f"{URL_VERIFIER}?code=INEXISTANT")
    assert resp.status_code == 200
    assert resp.data["valide"] is False


def test_verifier_code_expire(auth_client, bureau_a, chorale_a):
    code = auth_client(bureau_a).post(
        URL_LISTE, {"expire_le": "2020-01-01"}, format="json"
    ).data["code"]

    resp = APIClient().get(f"{URL_VERIFIER}?code={code}")
    assert resp.data["valide"] is False


# ---------------------------------------------------------------------------
# Auto-inscription publique
# ---------------------------------------------------------------------------

def _payload_inscription(code, **overrides):
    data = {
        "code": code, "username": "nouveau.choriste", "password": "provisoire123",
        "first_name": "Ama", "last_name": "Koffi", "email": "ama@example.com",
    }
    data.update(overrides)
    return data


def test_rejoindre_avec_code_valide_cree_membre_et_connecte(auth_client, bureau_a, chorale_a):
    code = auth_client(bureau_a).post(URL_LISTE, {}, format="json").data["code"]

    resp = APIClient().post(URL_REJOINDRE, _payload_inscription(code), format="json")
    assert resp.status_code == 201, resp.data
    assert "access" in resp.data and "refresh" in resp.data

    membre = Membre.objects.get(user__username="nouveau.choriste")
    assert membre.chorale_id == chorale_a.id
    assert membre.statut == Membre.Statut.ACTIF
    assert membre.invitation_utilisee.code == code

    invitation = InvitationChorale.objects.get(code=code)
    assert invitation.nombre_utilisations == 1


def test_rejoindre_pre_affecte_le_pupitre_suggere(auth_client, bureau_a, chorale_a):
    from membres.models import Pupitre
    pupitre = Pupitre.objects.create(chorale=chorale_a, nom="Basse", categorie="basse")
    code = auth_client(bureau_a).post(
        URL_LISTE, {"pupitre_suggere": pupitre.id}, format="json"
    ).data["code"]

    resp = APIClient().post(URL_REJOINDRE, _payload_inscription(code), format="json")
    assert resp.status_code == 201
    membre = Membre.objects.get(user__username="nouveau.choriste")
    assert membre.pupitre_id == pupitre.id


def test_rejoindre_code_invalide_refuse(auth_client, bureau_a):
    resp = APIClient().post(URL_REJOINDRE, _payload_inscription("INEXISTANT"), format="json")
    assert resp.status_code == 400
    assert Membre.objects.filter(user__username="nouveau.choriste").count() == 0


def test_rejoindre_code_desactive_refuse(auth_client, bureau_a):
    creation = auth_client(bureau_a).post(URL_LISTE, {}, format="json")
    code = creation.data["code"]
    invitation_id = InvitationChorale.objects.get(code=code).id
    auth_client(bureau_a).patch(f"{URL_LISTE}{invitation_id}/", {"is_active": False}, format="json")

    resp = APIClient().post(URL_REJOINDRE, _payload_inscription(code), format="json")
    assert resp.status_code == 400


def test_rejoindre_respecte_max_utilisations(auth_client, bureau_a):
    code = auth_client(bureau_a).post(URL_LISTE, {"max_utilisations": 1}, format="json").data["code"]

    premier = APIClient().post(URL_REJOINDRE, _payload_inscription(code), format="json")
    assert premier.status_code == 201

    second = APIClient().post(
        URL_REJOINDRE,
        _payload_inscription(code, username="second.choriste", email="second@example.com"),
        format="json",
    )
    assert second.status_code == 400
    assert Membre.objects.filter(user__username="second.choriste").count() == 0


def test_rejoindre_username_deja_pris_refuse(auth_client, bureau_a, membre_factory, chorale_a):
    existant = membre_factory(chorale_a)
    code = auth_client(bureau_a).post(URL_LISTE, {}, format="json").data["code"]

    resp = APIClient().post(
        URL_REJOINDRE, _payload_inscription(code, username=existant.user.username), format="json"
    )
    assert resp.status_code == 400


def test_throttle_rejoindre_bloque_apres_le_quota(auth_client, bureau_a):
    # DEFAULT_THROTTLE_RATES["invitation_rejoindre"] = "10/hour".
    code = auth_client(bureau_a).post(URL_LISTE, {"max_utilisations": 100}, format="json").data["code"]
    client = APIClient()
    for i in range(10):
        resp = client.post(
            URL_REJOINDRE,
            _payload_inscription(code, username=f"choriste{i}", email=f"c{i}@example.com"),
            format="json",
        )
        assert resp.status_code == 201, resp.data

    resp = client.post(
        URL_REJOINDRE,
        _payload_inscription(code, username="choriste_bloque", email="bloque@example.com"),
        format="json",
    )
    assert resp.status_code == 429
