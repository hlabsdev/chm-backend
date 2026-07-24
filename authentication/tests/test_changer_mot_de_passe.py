"""
Changement de mot de passe par l'utilisateur connecté
========================================================
"""

import pytest

pytestmark = pytest.mark.django_db

URL = "/api/auth/changer-mot-de-passe/"


def test_changement_reussi_puis_login_avec_le_nouveau(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)  # mot de passe = testpass123 (fixture)
    client = auth_client(membre)

    resp = client.post(URL, {"ancien": "testpass123", "nouveau": "NouveauPass!42"}, format="json")
    assert resp.status_code == 200

    membre.user.refresh_from_db()
    assert membre.user.check_password("NouveauPass!42")


def test_ancien_mot_de_passe_faux_refuse(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    resp = auth_client(membre).post(
        URL, {"ancien": "MAUVAIS", "nouveau": "NouveauPass!42"}, format="json"
    )
    assert resp.status_code == 400
    assert "ancien" in resp.data


def test_nouveau_mot_de_passe_faible_refuse(auth_client, membre_factory, chorale_a):
    membre = membre_factory(chorale_a)
    resp = auth_client(membre).post(
        URL, {"ancien": "testpass123", "nouveau": "12345678"}, format="json"
    )
    assert resp.status_code == 400
    assert "nouveau" in resp.data


def test_non_authentifie_refuse(api_client):
    resp = api_client.post(URL, {"ancien": "x", "nouveau": "y"}, format="json")
    assert resp.status_code == 401
