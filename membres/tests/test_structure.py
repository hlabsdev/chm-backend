"""
Module Membres — Structure (Pupitres, Postes, Organigramme)
=============================================================
Couvre le point 1.4 : gestion des pupitres/postes par le bureau, assignation
des groupes RBAC à un poste, endpoint des groupes assignables, et organigramme
lisible par tout membre.
"""

import pytest
from django.contrib.auth.models import Group

pytestmark = pytest.mark.django_db


@pytest.fixture
def bureau_a(membre_factory, mandat_factory, chorale_a):
    m = membre_factory(chorale_a)
    mandat_factory(m, "bureau")
    return m


# ---------------------------------------------------------------------------
# Pupitres CRUD
# ---------------------------------------------------------------------------

def test_bureau_cree_modifie_supprime_pupitre(auth_client, bureau_a, chorale_a):
    client = auth_client(bureau_a)

    cree = client.post(
        "/api/membres/pupitres/",
        {"nom": "Mezzo", "categorie": "mezzo", "ordre": 5},
        format="json",
    )
    assert cree.status_code == 201, cree.data
    pid = cree.data["id"]

    modif = client.patch(f"/api/membres/pupitres/{pid}/", {"ordre": 2}, format="json")
    assert modif.status_code == 200
    assert modif.data["ordre"] == 2

    suppr = client.delete(f"/api/membres/pupitres/{pid}/")
    assert suppr.status_code == 204


def test_membre_simple_ne_gere_pas_les_pupitres(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    resp = auth_client(membre).post(
        "/api/membres/pupitres/", {"nom": "X", "categorie": "autre"}, format="json"
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Postes + groupes RBAC
# ---------------------------------------------------------------------------

def test_bureau_cree_un_poste_avec_groupes_rbac(auth_client, bureau_a, groupes):
    """Le bureau crée un poste et lui rattache un groupe RBAC (permissions)."""
    client = auth_client(bureau_a)
    groupe_tresorier = Group.objects.get(name="tresorier")

    resp = client.post(
        "/api/membres/postes/",
        {
            "nom": "Trésorier adjoint", "type_poste": "bureau",
            "unique_actif": False, "groupes_ids": [groupe_tresorier.id],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert "tresorier" in resp.data["groupes_noms"]


def test_groupes_assignables_listes_pour_le_bureau(auth_client, bureau_a, groupes):
    resp = auth_client(bureau_a).get("/api/membres/groupes/")
    assert resp.status_code == 200
    noms = {g["name"] for g in resp.data}
    assert "bureau" in noms and "tresorier" in noms
    # Les groupes de base (gérés par le statut) ne sont pas proposés.
    assert "membre_actif" not in noms


def test_groupes_assignables_refuses_au_membre_simple(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    assert auth_client(membre).get("/api/membres/groupes/").status_code == 403


# ---------------------------------------------------------------------------
# Organigramme
# ---------------------------------------------------------------------------

def test_organigramme_visible_par_tout_membre(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """Un simple membre peut consulter l'organigramme (qui occupe quel poste)."""
    president = membre_factory(chorale_a)
    mandat_factory(president, "bureau")  # crée un poste + mandat actif
    simple = membre_factory(chorale_a)

    resp = auth_client(simple).get("/api/membres/postes/organigramme/")
    assert resp.status_code == 200
    # Au moins le poste du président pourvu, avec son nom.
    titulaires = [t["nom_complet"] for entree in resp.data for t in entree["titulaires"]]
    assert president.nom_complet in titulaires


def test_organigramme_isolation_tenant(
    auth_client, membre_factory, mandat_factory, chorale_a, chorale_b
):
    """L'organigramme de A ne révèle aucun titulaire de B."""
    pres_b = membre_factory(chorale_b)
    mandat_factory(pres_b, "bureau")
    membre_a = membre_factory(chorale_a)

    resp = auth_client(membre_a).get("/api/membres/postes/organigramme/")
    assert resp.status_code == 200
    titulaires = [t["nom_complet"] for entree in resp.data for t in entree["titulaires"]]
    assert pres_b.nom_complet not in titulaires
