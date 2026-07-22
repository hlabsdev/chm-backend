"""
Signal RBAC — sync_groupes_membre
===================================
Le signal post_save sur Mandat est l'unique source de vérité de
user.groups. Un mandat actif sur un poste lié au groupe 'tresorier'
doit ajouter ce groupe ; sa clôture doit le retirer.
"""

import pytest

from membres.models import Mandat, Poste

pytestmark = pytest.mark.django_db


def _groupes(membre):
    return set(membre.user.groups.values_list("name", flat=True))


def test_mandat_actif_ajoute_le_groupe(membre_factory, mandat_factory, chorale_a):
    """Créer un mandat actif 'tresorier' → groupe présent dans user.groups."""
    membre = membre_factory(chorale_a)

    mandat_factory(membre, "tresorier")

    assert "tresorier" in _groupes(membre)


def test_cloture_du_mandat_retire_le_groupe(membre_factory, mandat_factory, chorale_a):
    """Clôturer le mandat (is_active=False) → groupe retiré."""
    membre = membre_factory(chorale_a)
    mandat = mandat_factory(membre, "tresorier")
    assert "tresorier" in _groupes(membre)

    mandat.terminer()

    assert "tresorier" not in _groupes(membre)


def test_groupe_de_base_selon_statut(membre_factory, mandat_factory, chorale_a):
    """
    Le signal ajoute aussi le groupe de base (membre_actif) déduit du statut,
    en plus du groupe issu du mandat.
    """
    membre = membre_factory(chorale_a)

    mandat_factory(membre, "tresorier")

    assert {"membre_actif", "tresorier"} <= _groupes(membre)
