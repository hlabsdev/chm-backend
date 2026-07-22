"""
Vérification d'intégration de l'API (preuve fonctionnelle, pas visuelle)
========================================================================
Ces tests exercent les VRAIS endpoints de chaque module via le client HTTP
DRF, pour établir factuellement ce qui fonctionne bout-en-bout côté backend.
Ils servent de recette automatisée pour la checklist de juillet 2026.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# 0.1 — Authentification & session
# ---------------------------------------------------------------------------

class TestAuth:
    def test_login_renvoie_tokens_et_claims(self, membre_factory, mandat_factory, chorale_a):
        membre = membre_factory(chorale_a)
        mandat_factory(membre, "tresorier")
        client = APIClient()

        resp = client.post(
            "/api/auth/login/",
            {"username": membre.user.username, "password": "testpass123"},
            format="json",
        )

        assert resp.status_code == 200
        assert "access" in resp.data and "refresh" in resp.data

        # La devise de la chorale est portée par le token (défaut XOF).
        from rest_framework_simplejwt.tokens import AccessToken
        claims = AccessToken(resp.data["access"])
        assert claims["chorale_currency"] == "XOF"
        assert set(claims["groups"]) >= {"tresorier"}

    def test_refresh_renvoie_un_nouvel_access(self, membre_factory, chorale_a):
        membre = membre_factory(chorale_a)
        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"username": membre.user.username, "password": "testpass123"},
            format="json",
        )
        refresh = login.data["refresh"]

        resp = client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")

        assert resp.status_code == 200
        assert "access" in resp.data

    def test_mauvais_identifiants_401(self, membre_factory, chorale_a):
        membre = membre_factory(chorale_a)
        client = APIClient()
        resp = client.post(
            "/api/auth/login/",
            {"username": membre.user.username, "password": "WRONG"},
            format="json",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6 — Dashboard par rôle (endpoint réel /api/core/dashboard/)
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_membre_recoit_son_dashboard(self, auth_client, membre_factory, mandat_factory, chorale_a):
        membre = membre_factory(chorale_a)
        mandat_factory(membre, "maitre_choeur")
        client = auth_client(membre)

        resp = client.get("/api/core/dashboard/")

        assert resp.status_code == 200
        assert "role" in resp.data

    def test_superuser_dashboard_neutre_pas_400(self, db):
        User.objects.create_superuser("admin_it", "admin@it.test", "adminpass123")
        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"username": "admin_it", "password": "adminpass123"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        resp = client.get("/api/core/dashboard/")

        assert resp.status_code == 200
        assert resp.data["role"] == "staff"

    def test_utilisateur_sans_profil_membre_403(self, db):
        User.objects.create_user("orphan", password="orphanpass123")
        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"username": "orphan", "password": "orphanpass123"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        resp = client.get("/api/core/dashboard/")

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 1.4 — Pupitres (CRUD bureau)
# ---------------------------------------------------------------------------

class TestMembresStructure:
    def test_bureau_cree_et_liste_pupitre(self, auth_client, membre_factory, mandat_factory, chorale_a):
        bureau = membre_factory(chorale_a)
        mandat_factory(bureau, "bureau")
        client = auth_client(bureau)

        create = client.post(
            "/api/membres/pupitres/",
            {"nom": "Soprano", "categorie": "soprano", "ordre": 1},
            format="json",
        )
        assert create.status_code == 201

        liste = client.get("/api/membres/pupitres/")
        assert liste.status_code == 200
        assert liste.data["count"] == 1

    def test_membre_simple_ne_cree_pas_de_pupitre(self, auth_client, membre_factory, chorale_a):
        membre = membre_factory(chorale_a)
        client = auth_client(membre)
        resp = client.post(
            "/api/membres/pupitres/",
            {"nom": "Alto", "categorie": "alto"},
            format="json",
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3.1 — Répertoire musical (chants)
# ---------------------------------------------------------------------------

class TestMusique:
    def test_mdc_cree_un_chant_membre_le_lit(self, auth_client, membre_factory, mandat_factory, chorale_a):
        mdc = membre_factory(chorale_a)
        mandat_factory(mdc, "maitre_choeur")
        simple = membre_factory(chorale_a)

        client_mdc = auth_client(mdc)
        create = client_mdc.post(
            "/api/musique/chants/",
            {"titre": "Ave Maria", "compositeur": "Schubert", "style": "liturgique"},
            format="json",
        )
        assert create.status_code == 201, create.data

        client_simple = auth_client(simple)
        liste = client_simple.get("/api/musique/chants/")
        assert liste.status_code == 200
        assert liste.data["count"] == 1

    def test_membre_simple_ne_cree_pas_de_chant(self, auth_client, membre_factory, chorale_a):
        simple = membre_factory(chorale_a)
        client = auth_client(simple)
        resp = client.post(
            "/api/musique/chants/",
            {"titre": "X", "style": "liturgique"},
            format="json",
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4.1 — Finances : journal + état de caisse (solde agrégé backend)
# ---------------------------------------------------------------------------

class TestFinances:
    def test_tresorier_cree_mouvement_et_solde_agrege(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        client = auth_client(tresorier)

        # Catégorie puis deux mouvements (une entrée, une sortie).
        cat = client.post(
            "/api/finances/categories/",
            {"nom": "Dons", "type_mouvement": "entree"},
            format="json",
        )
        assert cat.status_code == 201, cat.data
        cat_id = cat.data["id"]

        e = client.post(
            "/api/finances/mouvements/",
            {"date": "2026-07-01", "montant": "100.00", "sens": "entree",
             "categorie": cat_id, "motif": "Don"},
            format="json",
        )
        s = client.post(
            "/api/finances/mouvements/",
            {"date": "2026-07-02", "montant": "30.00", "sens": "sortie",
             "categorie": cat_id, "motif": "Achat"},
            format="json",
        )
        assert e.status_code == 201, e.data
        assert s.status_code == 201, s.data

        etat = client.get("/api/finances/etat-caisse/")
        assert etat.status_code == 200
        assert float(etat.data["solde"]) == 70.0

    def test_journal_filtre_par_periode(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """Le filtre date_min/date_max du journal (front finances) fonctionne."""
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        client = auth_client(tresorier)
        cat = client.post(
            "/api/finances/categories/",
            {"nom": "Divers", "type_mouvement": "entree"}, format="json",
        ).data
        for d in ("2026-01-10", "2026-06-10"):
            client.post(
                "/api/finances/mouvements/",
                {"date": d, "montant": "10.00", "sens": "entree",
                 "categorie": cat["id"], "motif": "x"}, format="json",
            )

        resp = client.get("/api/finances/mouvements/?date_min=2026-05-01")

        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["date"] == "2026-06-10"

    def test_campagne_creation_et_liste_avec_taux(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """La liste des campagnes (front finances) expose le taux de recouvrement."""
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        client = auth_client(tresorier)

        create = client.post(
            "/api/finances/campagnes/",
            {"nom": "Uniformes 2026", "type_campagne": "ponctuelle",
             "montant_unitaire": "50.00", "date_debut": "2026-01-01"},
            format="json",
        )
        assert create.status_code == 201, create.data

        liste = client.get("/api/finances/campagnes/")
        assert liste.status_code == 200
        assert liste.data["count"] == 1
        assert "taux_recouvrement" in liste.data["results"][0]
