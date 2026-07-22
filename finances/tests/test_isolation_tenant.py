"""
Isolation multi-tenant — module finances
==========================================
Un membre de la chorale A ne doit JAMAIS pouvoir lire ni modifier une
ressource finances appartenant à la chorale B, même en étant trésorier
de sa propre chorale. Tests menés via l'API (pas directement sur le queryset).
"""

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def tresorier_a(membre_factory, mandat_factory, chorale_a):
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "tresorier")
    return membre


def test_tresorier_a_ne_peut_pas_lire_mouvement_de_b(
    auth_client, tresorier_a, mouvement_factory, chorale_b
):
    """Lecture d'une ressource d'une autre chorale → 404 (invisible)."""
    mouvement_b = mouvement_factory(chorale_b)
    client = auth_client(tresorier_a)

    resp = client.get(f"/api/finances/mouvements/{mouvement_b.pk}/")

    assert resp.status_code == 404


def test_tresorier_a_ne_peut_pas_modifier_mouvement_de_b(
    auth_client, tresorier_a, mouvement_factory, chorale_b
):
    """Modification d'une ressource d'une autre chorale → refusée (404/403)."""
    mouvement_b = mouvement_factory(chorale_b)
    client = auth_client(tresorier_a)

    resp = client.patch(
        f"/api/finances/mouvements/{mouvement_b.pk}/",
        {"motif": "PIRATAGE"},
        format="json",
    )

    assert resp.status_code in (403, 404)
    mouvement_b.refresh_from_db()
    assert mouvement_b.motif != "PIRATAGE"


def test_mouvement_de_b_absent_de_la_liste_vue_par_a(
    auth_client, tresorier_a, mouvement_factory, chorale_b
):
    """La liste renvoyée à A ne contient aucune ressource de B."""
    mouvement_b = mouvement_factory(chorale_b)
    client = auth_client(tresorier_a)

    resp = client.get("/api/finances/mouvements/")

    assert resp.status_code == 200
    ids = [m["id"] for m in resp.data["results"]]
    assert mouvement_b.pk not in ids


def test_tresorier_a_lit_bien_sa_propre_ressource(
    auth_client, tresorier_a, mouvement_factory, chorale_a
):
    """
    Discriminant : le trésorier DOIT voir la ressource de SA chorale.
    Si ce test échoue alors que les précédents passent, l'isolation
    « fonctionne » en réalité parce que plus personne ne voit rien
    (bug de résolution de request.chorale au niveau middleware/JWT).
    """
    mouvement_a = mouvement_factory(chorale_a, enregistre_par=tresorier_a)
    client = auth_client(tresorier_a)

    resp = client.get(f"/api/finances/mouvements/{mouvement_a.pk}/")

    assert resp.status_code == 200
    assert resp.data["id"] == mouvement_a.pk
