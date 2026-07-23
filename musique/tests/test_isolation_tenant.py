"""
Isolation multi-tenant — module musique
==========================================
Un maître de chœur de la chorale A ne doit JAMAIS pouvoir lire ni
modifier un Chant ou un Thème appartenant à la chorale B. Mêmes
scénarios que finances/tests/test_isolation_tenant.py (lecture,
modification, absence de la liste, contrôle positif), transposés au
répertoire musical qui n'avait encore aucun test d'isolation dédié.
"""

import pytest

from musique.models import Chant, Theme

pytestmark = pytest.mark.django_db


@pytest.fixture
def mdc_a(membre_factory, mandat_factory, chorale_a):
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "maitre_choeur")
    return membre


@pytest.fixture
def chant_factory(db):
    def _make(chorale, titre="Chant"):
        return Chant.objects.create(chorale=chorale, titre=titre, style=Chant.Style.AUTRE)
    return _make


def test_mdc_a_ne_peut_pas_lire_chant_de_b(auth_client, mdc_a, chant_factory, chorale_b):
    chant_b = chant_factory(chorale_b)
    client = auth_client(mdc_a)

    resp = client.get(f"/api/musique/chants/{chant_b.pk}/")

    assert resp.status_code == 404


def test_mdc_a_ne_peut_pas_modifier_chant_de_b(auth_client, mdc_a, chant_factory, chorale_b):
    chant_b = chant_factory(chorale_b)
    client = auth_client(mdc_a)

    resp = client.patch(
        f"/api/musique/chants/{chant_b.pk}/",
        {"titre": "PIRATAGE"},
        format="json",
    )

    assert resp.status_code == 404
    chant_b.refresh_from_db()
    assert chant_b.titre != "PIRATAGE"


def test_chant_de_b_absent_de_la_liste_vue_par_a(auth_client, mdc_a, chant_factory, chorale_b):
    chant_b = chant_factory(chorale_b)
    client = auth_client(mdc_a)

    resp = client.get("/api/musique/chants/")

    assert resp.status_code == 200
    ids = [c["id"] for c in resp.data["results"]]
    assert chant_b.pk not in ids


def test_mdc_a_lit_bien_son_propre_chant(auth_client, mdc_a, chant_factory, chorale_a):
    """Contrôle positif : sans lui, une isolation « qui bloque tout » passerait à tort."""
    chant_a = chant_factory(chorale_a)
    client = auth_client(mdc_a)

    resp = client.get(f"/api/musique/chants/{chant_a.pk}/")

    assert resp.status_code == 200
    assert resp.data["id"] == chant_a.pk


def test_theme_de_b_invisible_et_non_reutilisable_par_a(
    auth_client, mdc_a, chorale_a, chorale_b, chant_factory
):
    """
    Un thème de B ne doit ni fuiter dans la liste de A, ni être assignable
    à un chant de A (régression : themes_ids acceptait n'importe quel
    Theme.objects.all() non scopé par chorale).
    """
    theme_b = Theme.objects.create(chorale=chorale_b, nom="Thème B")
    chant_a = chant_factory(chorale_a)
    client = auth_client(mdc_a)

    liste = client.get("/api/musique/themes/")
    assert liste.status_code == 200
    assert theme_b.pk not in [t["id"] for t in liste.data["results"]]

    resp = client.patch(
        f"/api/musique/chants/{chant_a.pk}/",
        {"themes_ids": [theme_b.pk]},
        format="json",
    )
    assert resp.status_code == 400
    chant_a.refresh_from_db()
    assert theme_b not in chant_a.themes.all()
