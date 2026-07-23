"""
Provisionnement d'une nouvelle chorale — seule voie officielle d'onboarding
=============================================================================
Vérifie que la commande crée une chorale immédiatement utilisable (postes,
pupitres, catégories financières, premier compte Bureau avec un mandat actif
donnant bien accès au groupe `bureau`) et qu'elle refuse les doublons.
"""

import io

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Chorale
from finances.models import CategorieMouvement
from membres.models import Membre, Poste, Pupitre

pytestmark = pytest.mark.django_db


def _provision(**overrides):
    args = dict(
        nom="Chorale Test Provision",
        prefix="CTP",
        admin_username="president_ctp",
        admin_email="president@ctp.test",
        admin_first_name="Jean",
        admin_last_name="Dupont",
        admin_password="MotDePasse123!",
    )
    args.update(overrides)
    out = io.StringIO()
    call_command("provision_chorale", stdout=out, **{k.replace("-", "_"): v for k, v in args.items()})
    return out.getvalue()


def test_provision_chorale_cree_une_chorale_utilisable():
    _provision()

    chorale = Chorale.objects.get(nom="Chorale Test Provision")
    assert chorale.prefix == "CTP"
    assert chorale.currency == Chorale.Monnaie.XOF

    assert Pupitre.objects.filter(chorale=chorale).count() == 4
    assert Poste.objects.filter(chorale=chorale).count() == 8
    assert CategorieMouvement.objects.filter(chorale=chorale).count() == 11

    admin_user = User.objects.get(username="president_ctp")
    membre = admin_user.membre
    assert membre.chorale_id == chorale.id
    assert membre.mandats_actifs().count() == 1
    assert "bureau" in list(admin_user.groups.values_list("name", flat=True))


def test_provision_chorale_refuse_nom_duplique():
    _provision()
    with pytest.raises(CommandError):
        _provision(prefix="AUT", admin_username="autre_president")


def test_provision_chorale_refuse_prefix_duplique():
    _provision()
    with pytest.raises(CommandError):
        _provision(nom="Autre Chorale", admin_username="autre_president")


def test_provision_chorale_sans_mot_de_passe_en_genere_un():
    output = _provision(admin_password=None)
    assert "Mot de passe généré" in output
