"""
Demande d'adhésion chorale — formulaire public + modération
================================================================
Couvre l'anti-abus (throttle, honeypot, doublons) du formulaire public, et
la modération admin (approbation → provisionnement réel, rejet).
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from core.admin import DemandeChoraleAdmin
from core.models import Chorale, DemandeChorale

pytestmark = pytest.mark.django_db

URL = "/api/core/demandes-chorale/"


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    """Le throttle DRF est stocké dans le cache process — l'isoler par test."""
    cache.clear()
    yield
    cache.clear()


def _payload(**overrides):
    data = {
        "nom_chorale": "Chorale Test Adhésion",
        "prefix_souhaite": "CTA",
        "ville_pays": "Lomé, Togo",
        "contact_nom": "Awa Traoré",
        "contact_email": "awa@example.com",
        "contact_telephone": "90000000",
        "message": "Nous aimerions rejoindre la plateforme.",
    }
    data.update(overrides)
    return data


def test_demande_publique_creee_en_attente():
    resp = APIClient().post(URL, _payload(), format="json")
    assert resp.status_code == 201

    demande = DemandeChorale.objects.get(nom_chorale="Chorale Test Adhésion")
    assert demande.statut == DemandeChorale.Statut.EN_ATTENTE
    assert demande.contact_email == "awa@example.com"
    assert demande.adresse_ip  # capturée pour l'audit


def test_honeypot_simule_le_succes_sans_rien_creer():
    resp = APIClient().post(URL, _payload(site_web="http://spam.example"), format="json")
    assert resp.status_code == 201
    assert DemandeChorale.objects.count() == 0


def test_doublon_email_en_attente_refuse():
    APIClient().post(URL, _payload(), format="json")
    resp = APIClient().post(URL, _payload(nom_chorale="Autre Nom"), format="json")
    assert resp.status_code == 400


def test_doublon_nom_chorale_en_attente_refuse():
    APIClient().post(URL, _payload(), format="json")
    resp = APIClient().post(URL, _payload(contact_email="autre@example.com"), format="json")
    assert resp.status_code == 400


def test_meme_nom_reautorise_apres_rejet():
    """Une demande rejetée ne bloque pas une nouvelle tentative sous le même nom."""
    APIClient().post(URL, _payload(), format="json")
    DemandeChorale.objects.update(statut=DemandeChorale.Statut.REJETEE)

    resp = APIClient().post(URL, _payload(contact_email="nouveau@example.com"), format="json")
    assert resp.status_code == 201


def test_throttle_anti_abus_bloque_apres_le_quota():
    # DEFAULT_THROTTLE_RATES["demande_chorale"] = "5/day" (chm_config/settings.py).
    client = APIClient()
    for i in range(5):
        resp = client.post(URL, _payload(contact_email=f"u{i}@example.com", nom_chorale=f"Chorale {i}"), format="json")
        assert resp.status_code == 201, resp.data

    resp = client.post(URL, _payload(contact_email="u6@example.com", nom_chorale="Chorale 6"), format="json")
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Modération admin
# ---------------------------------------------------------------------------

@pytest.fixture
def demande_en_attente(db):
    return DemandeChorale.objects.create(
        nom_chorale="Chorale À Approuver", prefix_souhaite="CAA",
        contact_nom="Kofi Mensah", contact_email="kofi@example.com",
    )


@pytest.fixture
def admin_site():
    from django.contrib import admin
    return DemandeChoraleAdmin(DemandeChorale, admin.site)


def test_approbation_sans_prefix_attribue_est_refusee(demande_en_attente, admin_site, rf):
    request = rf.post("/admin/")
    request._messages = _MessagesStub()
    admin_site.approuver_et_provisionner(request, DemandeChorale.objects.filter(pk=demande_en_attente.pk))

    demande_en_attente.refresh_from_db()
    assert demande_en_attente.statut == DemandeChorale.Statut.EN_ATTENTE
    assert not Chorale.objects.filter(nom=demande_en_attente.nom_chorale).exists()


def test_approbation_avec_prefix_provisionne_la_chorale(demande_en_attente, admin_site, rf):
    demande_en_attente.prefix_attribue = "CAA"
    demande_en_attente.save()

    request = rf.post("/admin/")
    request._messages = _MessagesStub()
    admin_site.approuver_et_provisionner(request, DemandeChorale.objects.filter(pk=demande_en_attente.pk))

    demande_en_attente.refresh_from_db()
    assert demande_en_attente.statut == DemandeChorale.Statut.APPROUVEE
    assert demande_en_attente.chorale_creee is not None
    assert demande_en_attente.chorale_creee.prefix == "CAA"
    assert demande_en_attente.date_traitement is not None

    # La chorale est immédiatement utilisable : bureau + structure standard.
    from membres.models import Poste, Pupitre
    chorale = demande_en_attente.chorale_creee
    assert Pupitre.objects.filter(chorale=chorale).count() == 4
    assert Poste.objects.filter(chorale=chorale).count() == 8
    assert User.objects.filter(email="kofi@example.com").exists()


def test_rejet_marque_la_demande_sans_creer_de_chorale(demande_en_attente, admin_site, rf):
    request = rf.post("/admin/")
    request._messages = _MessagesStub()
    admin_site.rejeter(request, DemandeChorale.objects.filter(pk=demande_en_attente.pk))

    demande_en_attente.refresh_from_db()
    assert demande_en_attente.statut == DemandeChorale.Statut.REJETEE
    assert not Chorale.objects.filter(nom=demande_en_attente.nom_chorale).exists()


class _MessagesStub(list):
    """Évite de dépendre du middleware messages de Django dans ces tests unitaires."""
    def add(self, level, message, extra_tags=""):
        self.append((level, message))
