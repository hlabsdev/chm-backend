"""
Concurrence réelle sur les paiements de cotisation
====================================================
Voir membres/tests/test_concurrence.py pour la justification complète de
`transaction=True` et du skip hors PostgreSQL — même méthode ici.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connection, connections
from django.utils import timezone

from finances.models import CampagneCotisation, Cotisation

pytestmark = pytest.mark.django_db


def _exiger_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip(
            "Verrouillage non observable hors PostgreSQL : sur SQLite Django "
            "n'émet pas FOR UPDATE, le test serait un faux vert."
        )


@pytest.mark.django_db(transaction=True)
def test_paiements_concurrents_sur_une_cotisation_ne_perdent_pas_de_montant(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    """
    Deux paiements simultanés sur la MÊME cotisation doivent tous deux se
    comptabiliser : `cotisation.montant_paye` doit être la SOMME des deux, pas
    seulement l'un des deux (lost update).

    `PaiementCotisationSerializer.create()` fait
    `cotisation.montant_paye += montant` puis sauvegarde. Sans verrou sur la
    ligne Cotisation, deux transactions concurrentes lisent le même
    montant_paye de départ, et la seconde écriture écrase la première au lieu
    de s'additionner — de l'argent réellement encaissé (le Mouvement et le
    PaiementCotisation existent bien en base) disparaît du solde de la
    cotisation.
    """
    _exiger_postgresql()

    tresorier = membre_factory(chorale_a)
    mandat_factory(tresorier, "tresorier")
    membre_cible = membre_factory(chorale_a)

    campagne = CampagneCotisation.objects.create(
        chorale=chorale_a, nom="Campagne Concurrence",
        type_campagne=CampagneCotisation.TypeCampagne.PONCTUELLE,
        montant_unitaire=Decimal("20000"),
        date_debut=timezone.now().date(),
    )
    cotisation = Cotisation.objects.create(
        chorale=chorale_a, campagne=campagne, membre=membre_cible,
        montant_du=Decimal("20000"),
    )

    # Deux clients authentifiés distincts (login hors barrière) : la course à
    # tester porte sur l'écriture du paiement, pas sur l'authentification.
    client_a = auth_client(tresorier)
    client_b = auth_client(tresorier)

    depart = threading.Barrier(2, timeout=15)
    resultats = {}

    def payer(suffixe, client, montant):
        try:
            depart.wait()
            resp = client.post(
                "/api/finances/paiements/",
                {
                    "cotisation": cotisation.pk,
                    "montant": str(montant),
                    "date_paiement": str(timezone.now().date()),
                },
                format="json",
            )
            resultats[suffixe] = resp.status_code
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=payer, args=("premier", client_a, Decimal("7000"))),
        threading.Thread(target=payer, args=("second", client_b, Decimal("5000"))),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(resultats.values()) == [201, 201], (
        f"Les deux paiements devaient tous deux réussir (aucun conflit métier "
        f"entre eux, juste une course d'écriture) : {resultats}"
    )

    cotisation.refresh_from_db()
    assert cotisation.montant_paye == Decimal("12000"), (
        f"montant_paye devait être la somme des deux paiements (7000+5000=12000), "
        f"obtenu {cotisation.montant_paye} — un paiement a été perdu par écrasement."
    )
    assert cotisation.statut == Cotisation.StatutCotisation.PARTIEL
    assert cotisation.paiements.count() == 2
