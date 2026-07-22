"""
Permissions finances — RBAC via Mandat
========================================
Les endpoints finances sont réservés au bureau OU au trésorier
(IsBureauOrTresorier). Un membre actif sans mandat adéquat est refusé (403).
"""

import pytest

pytestmark = pytest.mark.django_db


def test_membre_actif_sans_mandat_refuse_sur_mouvements(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """
    Membre actif sans mandat trésorier ni bureau → 403 sur les mouvements.
    On lui donne un mandat 'maitre_choeur' pour prouver qu'un rôle
    quelconque ne suffit pas : seul bureau/trésorier ouvre les finances.
    """
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "maitre_choeur")
    client = auth_client(membre)

    resp = client.get("/api/finances/mouvements/")

    assert resp.status_code == 403


def test_membre_actif_sans_mandat_refuse_sur_etat_caisse(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """Même refus sur la vue non-ViewSet état-caisse."""
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "maitre_choeur")
    client = auth_client(membre)

    resp = client.get("/api/finances/etat-caisse/")

    assert resp.status_code == 403


def test_tresorier_accede_aux_mouvements(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """Un membre avec mandat trésorier passe (200)."""
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "tresorier")
    client = auth_client(membre)

    resp = client.get("/api/finances/mouvements/")

    assert resp.status_code == 200


def test_bureau_accede_aux_mouvements(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """Un membre avec mandat bureau passe aussi (200)."""
    membre = membre_factory(chorale_a)
    mandat_factory(membre, "bureau")
    client = auth_client(membre)

    resp = client.get("/api/finances/mouvements/")

    assert resp.status_code == 200
