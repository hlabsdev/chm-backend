"""
Notifications in-app + emails — déclenchement par les actions métier
=======================================================================
Vérifie que chaque cas métier crée bien les notifications attendues
(et un email quand la politique le prévoit), que le compteur non-lues et
les actions lue/tout-lu fonctionnent, et que l'isolation par destinataire
tient (un membre ne voit jamais les notifications d'un autre).
"""

import pytest
from django.core import mail

from notifications.models import Notification

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# API notifications (lecture, compteur, marquage)
# ---------------------------------------------------------------------------

def test_membre_ne_voit_que_ses_notifications(auth_client, membre_factory, chorale_a):
    m1 = membre_factory(chorale_a)
    m2 = membre_factory(chorale_a)
    Notification.objects.create(chorale=chorale_a, destinataire=m1, titre="Pour m1")
    Notification.objects.create(chorale=chorale_a, destinataire=m2, titre="Pour m2")

    resp = auth_client(m1).get("/api/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["titre"] == "Pour m1"


def test_compteur_non_lues_et_marquage(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    n1 = Notification.objects.create(chorale=chorale_a, destinataire=membre, titre="A")
    Notification.objects.create(chorale=chorale_a, destinataire=membre, titre="B")
    client = auth_client(membre)

    assert client.get("/api/notifications/non-lues/").data["count"] == 2

    assert client.post(f"/api/notifications/{n1.pk}/lue/").status_code == 200
    assert client.get("/api/notifications/non-lues/").data["count"] == 1

    assert client.post("/api/notifications/tout-lu/").data["count"] == 1
    assert client.get("/api/notifications/non-lues/").data["count"] == 0


# ---------------------------------------------------------------------------
# Déclenchements métier
# ---------------------------------------------------------------------------

def test_approbation_absence_notifie_le_demandeur_in_app_et_email(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    membre = membre_factory(chorale_a)
    membre.user.email = "choriste@example.com"
    membre.user.save()
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")

    demande = auth_client(membre).post(
        "/api/presences/permissions/",
        {"date_debut": "2026-08-01", "date_fin": "2026-08-03", "motif": "Voyage"},
        format="json",
    ).data
    auth_client(mdc).post(f"/api/presences/permissions/{demande['id']}/approuver/")

    notif = Notification.objects.filter(destinataire=membre, type_notification="permission")
    assert notif.count() == 1
    assert "approuvée" in notif.first().titre.lower()
    assert len(mail.outbox) == 1
    assert "choriste@example.com" in mail.outbox[0].to


def test_attribution_mandat_notifie_le_membre(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    cible = membre_factory(chorale_a)

    from membres.models import Poste
    poste = Poste.objects.create(chorale=chorale_a, nom="Secrétaire", type_poste="bureau")
    resp = auth_client(bureau).post(
        "/api/membres/mandats/",
        {"membre": cible.pk, "poste": poste.pk, "date_debut": "2026-08-01"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert Notification.objects.filter(destinataire=cible, type_notification="mandat").exists()


def test_annonce_notifie_tous_les_membres_actifs_sauf_auteur(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    m1 = membre_factory(chorale_a)
    m2 = membre_factory(chorale_a)

    auth_client(bureau).post(
        "/api/communications/annonces/",
        {"titre": "Concert", "contenu": "Répétition générale samedi."},
        format="json",
    )

    assert Notification.objects.filter(type_notification="annonce").count() == 2
    assert not Notification.objects.filter(destinataire=bureau, type_notification="annonce").exists()
    assert Notification.objects.filter(destinataire=m1, type_notification="annonce").exists()
    # Pas d'email de masse pour une annonce.
    assert len(mail.outbox) == 0


def test_generation_cotisations_notifie_les_membres(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    tresorier = membre_factory(chorale_a)
    mandat_factory(tresorier, "tresorier")
    choriste = membre_factory(chorale_a)
    client = auth_client(tresorier)

    camp = client.post(
        "/api/finances/campagnes/",
        {"nom": "Annuelle", "type_campagne": "annuelle", "montant_unitaire": "20.00", "date_debut": "2026-01-01"},
        format="json",
    ).data
    client.post(f"/api/finances/campagnes/{camp['id']}/generer/")

    assert Notification.objects.filter(destinataire=choriste, type_notification="cotisation").exists()
