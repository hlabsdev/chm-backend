"""
Isolation multi-tenant — module membres
==========================================
Un membre du Bureau de la chorale A ne doit JAMAIS pouvoir lire ni
modifier un Membre ou un Pupitre appartenant à la chorale B. Mêmes
scénarios que finances/tests/test_isolation_tenant.py (lecture,
modification, absence de la liste, contrôle positif), transposés au
module membres qui n'avait encore aucun test d'isolation dédié.
"""

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def bureau_a(membre_factory, mandat_factory, chorale_a):
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "bureau")
    return membre


def test_bureau_a_ne_peut_pas_lire_membre_de_b(auth_client, bureau_a, membre_factory, chorale_b):
    membre_b = membre_factory(chorale_b)
    client = auth_client(bureau_a)

    resp = client.get(f"/api/membres/{membre_b.pk}/")

    assert resp.status_code == 404


def test_bureau_a_ne_peut_pas_modifier_membre_de_b(auth_client, bureau_a, membre_factory, chorale_b):
    membre_b = membre_factory(chorale_b)
    client = auth_client(bureau_a)

    resp = client.patch(
        f"/api/membres/{membre_b.pk}/",
        {"telephone": "PIRATAGE"},
        format="json",
    )

    assert resp.status_code == 404
    membre_b.refresh_from_db()
    assert membre_b.telephone != "PIRATAGE"


def test_membre_de_b_absent_de_la_liste_vue_par_a(auth_client, bureau_a, membre_factory, chorale_b):
    membre_b = membre_factory(chorale_b)
    client = auth_client(bureau_a)

    resp = client.get("/api/membres/?page_size=100")

    assert resp.status_code == 200
    ids = [m["id"] for m in resp.data["results"]]
    assert membre_b.pk not in ids


def test_bureau_a_lit_bien_son_propre_membre(auth_client, bureau_a, membre_factory, chorale_a):
    """Contrôle positif : sans lui, une isolation « qui bloque tout » passerait à tort."""
    membre_a = membre_factory(chorale_a)
    client = auth_client(bureau_a)

    resp = client.get(f"/api/membres/{membre_a.pk}/")

    assert resp.status_code == 200
    assert resp.data["id"] == membre_a.pk


def test_pupitre_de_b_invisible_et_non_modifiable_par_a(auth_client, bureau_a, chorale_b):
    from membres.models import Pupitre
    pupitre_b = Pupitre.objects.create(chorale=chorale_b, nom="Soprano B", categorie="soprano")
    client = auth_client(bureau_a)

    assert client.get(f"/api/membres/pupitres/{pupitre_b.pk}/").status_code == 404
    resp = client.patch(f"/api/membres/pupitres/{pupitre_b.pk}/", {"nom": "PIRATAGE"}, format="json")
    assert resp.status_code == 404
    pupitre_b.refresh_from_db()
    assert pupitre_b.nom != "PIRATAGE"
