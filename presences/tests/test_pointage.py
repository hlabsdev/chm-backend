"""
Pointage de présence — points de rupture
==========================================
L'écran mobile de pointage persiste chaque tap immédiatement via
POST /api/presences/pointages/ (upsert). Tests ciblés :
- refus d'écriture pour un membre sans mandat MDC/bureau ;
- idempotence de l'upsert (retry réseau = pas de doublon ni d'erreur) ;
- isolation tenant sur l'écriture (pointer la répétition d'une autre chorale).
"""

import pytest

from presences.models import Presence, Repetition

pytestmark = pytest.mark.django_db

URL = "/api/presences/pointages/"


@pytest.fixture
def repetition_factory(db):
    def _make(chorale, date="2026-07-15"):
        return Repetition.objects.create(
            chorale=chorale, date=date, heure_debut="19:00"
        )
    return _make


def test_flux_demande_de_permission(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """2.3 : un membre soumet une demande d'absence, le MDC l'approuve."""
    membre = membre_factory(chorale_a)
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")

    client_membre = auth_client(membre)
    demande = client_membre.post(
        "/api/presences/permissions/",
        {"date_debut": "2026-08-01", "date_fin": "2026-08-03", "motif": "Voyage"},
        format="json",
    )
    assert demande.status_code == 201, demande.data
    assert demande.data["statut"] == "en_attente"
    demande_id = demande.data["id"]

    # Le membre ne peut pas approuver sa propre demande.
    refus = client_membre.post(f"/api/presences/permissions/{demande_id}/approuver/")
    assert refus.status_code == 403

    # Le MDC approuve.
    client_mdc = auth_client(mdc)
    ok = client_mdc.post(f"/api/presences/permissions/{demande_id}/approuver/")
    assert ok.status_code == 200

    from presences.models import PermissionRequest
    assert PermissionRequest.objects.get(pk=demande_id).statut == "approuvee"


def test_confidentialite_liste_permissions(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """Un membre lambda ne voit que ses demandes ; le MDC voit tout."""
    m1 = membre_factory(chorale_a)
    m2 = membre_factory(chorale_a)
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")

    for membre in (m1, m2):
        auth_client(membre).post(
            "/api/presences/permissions/",
            {"date_debut": "2026-08-01", "date_fin": "2026-08-02", "motif": "x"},
            format="json",
        )

    # m1 ne voit que sa propre demande.
    liste_m1 = auth_client(m1).get("/api/presences/permissions/")
    assert liste_m1.data["count"] == 1
    assert liste_m1.data["results"][0]["membre"] == m1.pk

    # Le MDC voit les deux.
    liste_mdc = auth_client(mdc).get("/api/presences/permissions/")
    assert liste_mdc.data["count"] == 2


def test_bureau_redige_le_resume_de_seance(
    auth_client, membre_factory, mandat_factory, chorale_a, repetition_factory
):
    """
    Résumé/compte-rendu de répétition (décisions, annonces) — généralement
    rédigé par le secrétaire (bureau). Un simple membre ne peut pas l'éditer.
    """
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    membre = membre_factory(chorale_a)
    rep = repetition_factory(chorale_a)

    resp = auth_client(bureau).patch(
        f"/api/presences/repetitions/{rep.pk}/",
        {"resume": "Décision : concert de Noël le 20 décembre."},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["resume"] == "Décision : concert de Noël le 20 décembre."

    refus = auth_client(membre).patch(
        f"/api/presences/repetitions/{rep.pk}/",
        {"resume": "Je modifie sans droit."},
        format="json",
    )
    assert refus.status_code == 403


def test_mdc_cree_une_repetition_avec_chorale_injectee(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """
    Création de répétition via l'API : la chorale du user doit être injectée
    automatiquement (RepetitionDetailSerializer n'expose pas le champ chorale).
    Régression : sans perform_create explicite → IntegrityError chorale_id NULL.
    """
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")
    client = auth_client(mdc)

    resp = client.post(
        "/api/presences/repetitions/",
        {"date": "2026-08-01", "heure_debut": "19:00", "lieu": "Salle A"},
        format="json",
    )

    assert resp.status_code == 201
    rep = Repetition.objects.get(pk=resp.data["id"])
    assert rep.chorale_id == chorale_a.id
    # Le créateur (MDC) est désigné dirigeant par défaut.
    assert rep.dirigee_par_id == mdc.id


def test_membre_sans_mandat_refuse_en_ecriture(
    auth_client, membre_factory, chorale_a, repetition_factory
):
    """Un simple membre actif ne peut pas pointer → 403."""
    membre = membre_factory(chorale_a)
    rep = repetition_factory(chorale_a)
    client = auth_client(membre)

    resp = client.post(
        URL,
        {"repetition": rep.pk, "membre": membre.pk, "statut": "present"},
        format="json",
    )

    assert resp.status_code == 403
    assert Presence.objects.count() == 0


def test_upsert_idempotent_pour_mdc(
    auth_client, membre_factory, mandat_factory, chorale_a, repetition_factory
):
    """
    Le MDC pointe un choriste (201), re-poste le même couple avec un autre
    statut (200) : une seule ligne, statut mis à jour — jamais d'erreur
    d'unicité sur un retry.
    """
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")
    choriste = membre_factory(chorale_a)
    rep = repetition_factory(chorale_a)
    client = auth_client(mdc)

    r1 = client.post(
        URL, {"repetition": rep.pk, "membre": choriste.pk, "statut": "present"},
        format="json",
    )
    r2 = client.post(
        URL, {"repetition": rep.pk, "membre": choriste.pk, "statut": "retard"},
        format="json",
    )

    assert r1.status_code == 201
    assert r2.status_code == 200
    presences = Presence.objects.filter(repetition=rep, membre=choriste)
    assert presences.count() == 1
    assert presences.first().statut == "retard"


def test_mdc_ne_peut_pas_pointer_une_repetition_d_une_autre_chorale(
    auth_client, membre_factory, mandat_factory, chorale_a, chorale_b,
    repetition_factory,
):
    """Écriture cross-tenant refusée (404, existence non révélée)."""
    mdc_a = membre_factory(chorale_a)
    mandat_factory(mdc_a, "maitre_choeur")
    choriste_b = membre_factory(chorale_b)
    rep_b = repetition_factory(chorale_b)
    client = auth_client(mdc_a)

    resp = client.post(
        URL,
        {"repetition": rep_b.pk, "membre": choriste_b.pk, "statut": "present"},
        format="json",
    )

    assert resp.status_code == 404
    assert Presence.objects.count() == 0
