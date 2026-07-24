"""
Concurrence réelle sur les chemins protégés par `select_for_update`
====================================================================
Ces tests exigent `transaction=True` : un `TestCase` Django classique
enveloppe chaque test dans UNE transaction, ce qui empêche deux connexions de
s'observer et produirait un faux vert — le verrou paraîtrait fonctionner alors
qu'il n'a jamais été mis à l'épreuve.

Ils exigent aussi PostgreSQL. Sur SQLite, `has_select_for_update` vaut False :
Django n'émet alors tout simplement pas la clause `FOR UPDATE` (sans lever
d'erreur), donc le verrou ne protège rien. C'est précisément le genre de
comportement masqué que la bascule PostgreSQL doit révéler — d'où le skip
explicite plutôt qu'une assertion affaiblie.
"""

import threading

import pytest
from django.contrib.auth.models import User
from django.db import connection, connections, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Chorale
from membres.models import InvitationChorale, Mandat, Membre, Poste

URL_REJOINDRE = "/api/membres/invitations/rejoindre/"


def _exiger_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip(
            "Verrouillage non observable hors PostgreSQL : sur SQLite Django "
            "n'émet pas FOR UPDATE, le test serait un faux vert."
        )


def _payload(code, suffixe):
    return {
        "code": code,
        "username": f"choriste.{suffixe}",
        "password": "MotDePasseSolide!42",
        "first_name": "Ama",
        "last_name": "Koffi",
        "email": f"{suffixe}@example.com",
    }


@pytest.mark.django_db(transaction=True)
def test_invitation_a_usage_unique_resiste_a_deux_inscriptions_simultanees():
    """
    Deux choristes soumettent le même code `max_utilisations=1` au même instant.
    Le `select_for_update()` de `RejoindreInvitationSerializer.create()` doit
    sérialiser les deux transactions : exactement une inscription aboutit.

    Sans verrou effectif, les deux passent la validation (qui lit
    `nombre_utilisations=0`) et deux membres sont créés pour une invitation
    nominative.
    """
    _exiger_postgresql()

    chorale = Chorale.objects.create(
        nom="Chorale Concurrence", prefix="CCC", date_creation="2020-01-01"
    )
    invitation = InvitationChorale.objects.create(
        chorale=chorale, code="CONCUR01", max_utilisations=1
    )

    depart = threading.Barrier(2, timeout=15)
    statuts = {}

    def rejoindre(suffixe):
        try:
            # Aligne les deux requêtes sur le même instant : sans cette
            # barrière, la première finirait avant que la seconde ne commence
            # et le test redeviendrait séquentiel.
            depart.wait()
            reponse = APIClient().post(
                URL_REJOINDRE, _payload(invitation.code, suffixe), format="json"
            )
            statuts[suffixe] = reponse.status_code
        finally:
            # Chaque thread ouvre sa propre connexion : la refermer évite de
            # laisser des connexions ouvertes qui bloqueraient le teardown.
            connections.close_all()

    threads = [
        threading.Thread(target=rejoindre, args=(suffixe,), daemon=True)
        for suffixe in ("premier", "second")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(statuts.values()) == [201, 400], (
        f"Une seule inscription devait aboutir, obtenu : {statuts}"
    )

    invitation.refresh_from_db()
    assert invitation.nombre_utilisations == 1
    assert Membre.objects.filter(chorale=chorale).count() == 1


@pytest.mark.django_db(transaction=True)
def test_matricules_concurrents_restent_uniques_dans_une_chorale():
    """
    Deux membres créés au même instant dans la même chorale doivent recevoir
    deux matricules distincts et consécutifs.

    `Membre.generer_numero()` lit le plus grand suffixe existant puis
    incrémente. Sans verrou sur la ligne `Chorale`, deux transactions
    simultanées lisent le même « dernier numéro », calculent le même suffixe,
    et la seconde meurt sur la contrainte d'unicité `numero_membre`
    (IntegrityError → 500 côté API) au lieu d'obtenir le numéro suivant.

    Ce chemin n'est PAS couvert par le test d'invitation ci-dessus : celui-ci
    est protégé par le verrou de l'invitation. Ici on exerce la création
    directe (Bureau, import, seed), qui n'a pas d'autre garde-fou.
    """
    _exiger_postgresql()

    chorale = Chorale.objects.create(
        nom="Chorale Matricules", prefix="MAT", date_creation="2020-01-01"
    )

    depart = threading.Barrier(2, timeout=15)
    resultats = {}

    def creer(suffixe):
        try:
            depart.wait()
            with transaction.atomic():
                user = User.objects.create_user(
                    username=f"membre.{suffixe}",
                    password="MotDePasseSolide!42",
                    first_name="Ama",
                    last_name="Koffi",
                )
                membre = Membre.objects.create(
                    user=user,
                    chorale=chorale,
                    numero_membre=Membre.generer_numero(chorale),
                    date_adhesion=timezone.now().date(),
                    statut=Membre.Statut.ACTIF,
                )
            resultats[suffixe] = membre.numero_membre
        except Exception as exc:  # noqa: BLE001 — on veut le diagnostic exact
            resultats[suffixe] = f"ERREUR {type(exc).__name__}: {exc}"
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=creer, args=(suffixe,), daemon=True)
        for suffixe in ("premier", "second")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    obtenus = sorted(resultats.values())
    assert obtenus == ["MAT-0001", "MAT-0002"], (
        f"Les deux créations devaient obtenir des matricules consécutifs, "
        f"obtenu : {resultats}"
    )
    assert Membre.objects.filter(chorale=chorale).count() == 2


@pytest.mark.django_db(transaction=True)
def test_poste_unique_actif_resiste_a_deux_attributions_simultanees(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """
    PRIORITAIRE (cf. §10.3 du plan) : ce mécanisme sera refondu au prochain
    jalon RBAC — ce test est le filet qui doit tenir en attendant.

    Deux membres du Bureau attribuent, au même instant, le même poste
    `unique_actif=True` à deux membres DIFFÉRENTS. La contrainte DB
    `unique_mandat_actif_par_membre_poste` ne porte que sur (membre, poste) :
    rien au niveau SQL n'empêche deux membres distincts d'avoir chacun un
    mandat actif sur le même poste unique_actif. Seule
    `Mandat.verrouiller_poste_pour_unicite()` (verrou + revalidation dans
    MandatSerializer.create) ferme cette fenêtre.
    """
    _exiger_postgresql()

    poste = Poste.objects.create(
        chorale=chorale_a, nom="Présidente Concurrence",
        type_poste=Poste.TypePoste.BUREAU, unique_actif=True,
    )
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    candidat_a = membre_factory(chorale_a)
    candidat_b = membre_factory(chorale_a)
    # Deux clients authentifiés distincts (login hors barrière) : la course
    # à tester porte sur l'écriture du mandat, pas sur l'authentification.
    client_a = auth_client(bureau)
    client_b = auth_client(bureau)

    depart = threading.Barrier(2, timeout=15)
    resultats = {}

    def attribuer(suffixe, client, candidat):
        try:
            depart.wait()
            resp = client.post(
                "/api/membres/mandats/",
                {
                    "membre": candidat.pk,
                    "poste": poste.pk,
                    "date_debut": "2026-01-01",
                    "is_active": True,
                },
                format="json",
            )
            resultats[suffixe] = resp.status_code
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=attribuer, args=("premier", client_a, candidat_a)),
        threading.Thread(target=attribuer, args=("second", client_b, candidat_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(resultats.values()) == [201, 400], (
        f"Une seule attribution devait aboutir, obtenu : {resultats}"
    )
    actifs = Mandat.objects.filter(poste=poste, is_active=True)
    assert actifs.count() == 1, (
        f"Un seul mandat actif attendu sur ce poste unique_actif, "
        f"obtenu : {list(actifs.values_list('membre_id', flat=True))}"
    )
