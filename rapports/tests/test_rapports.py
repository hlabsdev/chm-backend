"""
Module Rapports — agrégation & permissions
=============================================
Vérifie que chaque rapport agrège les vraies données de LA chorale du
user (jamais celles d'un autre tenant), et que les permissions collent :
financier réservé bureau/trésorier, les autres bureau/MDC.
"""

from decimal import Decimal

import pytest

from communications.models import Annonce  # noqa: F401 (garantit le chargement de l'app)
from finances.models import CategorieMouvement, Mouvement
from musique.models import Chant, SeanceChant, Theme
from presences.models import Presence, Repetition

pytestmark = pytest.mark.django_db


@pytest.fixture
def bureau_a(membre_factory, mandat_factory, chorale_a):
    m = membre_factory(chorale_a)
    mandat_factory(m, "bureau")
    return m


# ---------------------------------------------------------------------------
# Financier
# ---------------------------------------------------------------------------

def test_rapport_financier_agrege_entrees_sorties_et_solde(
    auth_client, bureau_a, chorale_a, mouvement_factory
):
    cat_sortie, _ = CategorieMouvement.objects.get_or_create(
        chorale=chorale_a, nom="Transport", defaults={"type_mouvement": "sortie"}
    )
    mouvement_factory(chorale_a, enregistre_par=bureau_a)  # entrée 1000
    Mouvement.objects.create(
        chorale=chorale_a, date="2025-02-01", montant="300.00", sens="sortie",
        categorie=cat_sortie, motif="Bus", enregistre_par=bureau_a,
    )

    resp = auth_client(bureau_a).get("/api/rapports/financier/")
    assert resp.status_code == 200
    assert resp.data["total_entrees"] == Decimal("1000.00")
    assert resp.data["total_sorties"] == Decimal("300.00")
    assert resp.data["solde"] == Decimal("700.00")


def test_rapport_financier_refuse_maitre_choeur(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")
    resp = auth_client(mdc).get("/api/rapports/financier/")
    assert resp.status_code == 403


def test_rapport_financier_isolation_tenant(
    auth_client, bureau_a, chorale_b, mouvement_factory
):
    """Un mouvement de la chorale B ne doit pas compter dans le rapport de A."""
    mouvement_factory(chorale_b)  # entrée dans B uniquement
    resp = auth_client(bureau_a).get("/api/rapports/financier/")
    assert resp.status_code == 200
    assert resp.data["total_entrees"] == Decimal("0")


def test_rapport_financier_filtre_periode(
    auth_client, bureau_a, chorale_a
):
    cat, _ = CategorieMouvement.objects.get_or_create(
        chorale=chorale_a, nom="Don", defaults={"type_mouvement": "entree"}
    )
    Mouvement.objects.create(chorale=chorale_a, date="2025-01-10", montant="100.00", sens="entree", categorie=cat, motif="A", enregistre_par=bureau_a)
    Mouvement.objects.create(chorale=chorale_a, date="2025-06-10", montant="500.00", sens="entree", categorie=cat, motif="B", enregistre_par=bureau_a)

    resp = auth_client(bureau_a).get("/api/rapports/financier/?date_debut=2025-05-01&date_fin=2025-12-31")
    assert resp.data["total_entrees"] == Decimal("500.00")


# ---------------------------------------------------------------------------
# Présences
# ---------------------------------------------------------------------------

def test_rapport_presences_taux_global_et_par_membre(
    auth_client, bureau_a, membre_factory, chorale_a
):
    choriste = membre_factory(chorale_a)
    rep1 = Repetition.objects.create(chorale=chorale_a, date="2026-01-05", heure_debut="19:00")
    rep2 = Repetition.objects.create(chorale=chorale_a, date="2026-01-12", heure_debut="19:00")
    Presence.objects.create(chorale=chorale_a, repetition=rep1, membre=choriste, statut="present")
    Presence.objects.create(chorale=chorale_a, repetition=rep2, membre=choriste, statut="absent")

    resp = auth_client(bureau_a).get("/api/rapports/presences/")
    assert resp.status_code == 200
    assert resp.data["nombre_repetitions"] == 2
    assert resp.data["taux_global"] == 50.0
    ligne = next(l for l in resp.data["par_membre"] if l["membre"] == choriste.nom_complet)
    assert ligne["presents"] == 1
    assert ligne["absents"] == 1
    assert ligne["taux"] == 50.0


def test_rapport_presences_accessible_maitre_choeur(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")
    resp = auth_client(mdc).get("/api/rapports/presences/")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Effectifs
# ---------------------------------------------------------------------------

def test_rapport_effectifs_compte_par_statut(
    auth_client, bureau_a, membre_factory, chorale_a
):
    membre_factory(chorale_a, statut="honoraire")
    resp = auth_client(bureau_a).get("/api/rapports/effectifs/")
    assert resp.status_code == 200
    # bureau_a est actif ; le membre ajouté est honoraire.
    actifs = next(s["count"] for s in resp.data["par_statut"] if s["statut"] == "Actif")
    honoraires = next(s["count"] for s in resp.data["par_statut"] if s["statut"] == "Honoraire")
    assert actifs >= 1
    assert honoraires == 1


# ---------------------------------------------------------------------------
# Répertoire
# ---------------------------------------------------------------------------

def test_rapport_repertoire_par_statut_apprentissage(
    auth_client, bureau_a, chorale_a
):
    theme = Theme.objects.create(chorale=chorale_a, nom="Louange")
    chant = Chant.objects.create(chorale=chorale_a, titre="Gloria", style="liturgique")
    chant.themes.add(theme)
    autre = Chant.objects.create(chorale=chorale_a, titre="Silencieux", style="autre")  # jamais travaillé
    rep = Repetition.objects.create(chorale=chorale_a, date="2026-02-01", heure_debut="19:00")
    SeanceChant.objects.create(chorale=chorale_a, repetition=rep, chant=chant, statut="maitrise")

    resp = auth_client(bureau_a).get("/api/rapports/repertoire/")
    assert resp.status_code == 200
    assert resp.data["total"] == 2
    maitrise = next(s["count"] for s in resp.data["par_statut"] if s["statut"] == "Maîtrisé")
    jamais = next(s["count"] for s in resp.data["par_statut"] if s["statut"] == "Jamais travaillé")
    assert maitrise == 1
    assert jamais == 1
    assert resp.data["par_theme"][0]["theme"] == "Louange"
