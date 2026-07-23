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

    def test_dashboard_solde_visible_tresorier_pas_mdc(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """Le solde n'apparaît que pour le staff finance (pas pour un MDC)."""
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        mdc = membre_factory(chorale_a)
        mandat_factory(mdc, "maitre_choeur")

        d_tres = auth_client(tresorier).get("/api/core/dashboard/")
        assert d_tres.status_code == 200
        assert d_tres.data.get("solde") is not None

        d_mdc = auth_client(mdc).get("/api/core/dashboard/")
        assert d_mdc.status_code == 200
        assert d_mdc.data.get("solde") is None

    def test_dashboard_choriste_cotisation_status_reel(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """Le statut de cotisation du choriste est calculé, pas mocké."""
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        choriste = membre_factory(chorale_a)

        # Sans aucune cotisation : message neutre, pas "À jour" par défaut.
        d0 = auth_client(choriste).get("/api/core/dashboard/")
        assert d0.data["cotisation_status"] == "Aucune cotisation"

        client_t = auth_client(tresorier)
        camp = client_t.post(
            "/api/finances/campagnes/",
            {"nom": "C", "type_campagne": "annuelle", "montant_unitaire": "20.00", "date_debut": "2026-01-01"},
            format="json",
        ).data
        client_t.post(f"/api/finances/campagnes/{camp['id']}/generer/")

        d1 = auth_client(choriste).get("/api/core/dashboard/")
        assert d1.data["cotisation_status"] == "Impayée"

    def test_dashboard_programme_enrichi_compositeur_themes_notes(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """
        La carte Programme du dashboard staff ne se limite plus à titre+statut :
        compositeur, style, thèmes (tags) et notes de séance doivent apparaître.
        """
        from musique.models import Chant, SeanceChant, Theme
        from presences.models import Repetition

        mdc = membre_factory(chorale_a)
        mandat_factory(mdc, "maitre_choeur")

        theme = Theme.objects.create(chorale=chorale_a, nom="Noël")
        chant = Chant.objects.create(
            chorale=chorale_a, titre="Douce Nuit", compositeur="F. Gruber",
            style=Chant.Style.LITURGIQUE,
        )
        chant.themes.add(theme)
        rep = Repetition.objects.create(chorale=chorale_a, date="2026-12-20", heure_debut="19:00")
        SeanceChant.objects.create(
            chorale=chorale_a, repetition=rep, chant=chant,
            statut=SeanceChant.StatutApprentissage.EN_TRAVAIL,
            notes="Attention à la respiration au refrain.",
        )

        resp = auth_client(mdc).get("/api/core/dashboard/")

        assert resp.status_code == 200
        item = resp.data["programme"][0]
        assert item["titre"] == "Douce Nuit"
        assert item["compositeur"] == "F. Gruber"
        assert item["style"] == "liturgique"
        assert item["themes"] == ["Noël"]
        assert item["notes"] == "Attention à la respiration au refrain."

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

    def test_bureau_cree_un_membre_avec_compte(self, auth_client, membre_factory, mandat_factory, chorale_a):
        """Création membre (1.2) : User + Membre créés, numero_membre auto, login possible."""
        bureau = membre_factory(chorale_a)
        mandat_factory(bureau, "bureau")
        client = auth_client(bureau)

        resp = client.post(
            "/api/membres/",
            {
                "username": "nouveau.choriste", "password": "provisoire123",
                "first_name": "Ama", "last_name": "Koffi",
                "email": "ama@example.com", "statut": "actif",
                "date_adhesion": "2026-07-01",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["numero_membre"].startswith(chorale_a.prefix)

        # Le compte créé permet de se connecter.
        from rest_framework.test import APIClient
        login = APIClient().post(
            "/api/auth/login/",
            {"username": "nouveau.choriste", "password": "provisoire123"},
            format="json",
        )
        assert login.status_code == 200

    def test_bureau_modifie_et_soft_delete_un_membre(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """1.2 : édition (User+Membre) puis suppression logique par le bureau."""
        bureau = membre_factory(chorale_a)
        mandat_factory(bureau, "bureau")
        cible = membre_factory(chorale_a)
        client = auth_client(bureau)

        patch = client.patch(
            f"/api/membres/{cible.pk}/",
            {"first_name": "Nouveau", "telephone": "0102030405", "statut": "honoraire"},
            format="json",
        )
        assert patch.status_code == 200, patch.data
        cible.refresh_from_db()
        cible.user.refresh_from_db()
        assert cible.user.first_name == "Nouveau"
        assert cible.statut == "honoraire"

        # Suppression = soft-delete (le membre disparaît de la liste).
        delete = client.delete(f"/api/membres/{cible.pk}/")
        assert delete.status_code == 204
        cible.refresh_from_db()
        assert cible.is_deleted is True
        liste = client.get("/api/membres/?page_size=100")
        assert cible.pk not in [m["id"] for m in liste.data["results"]]

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

    def test_themes_creation_et_filtre_repertoire(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """
        Thèmes = tags réutilisables sur les chants (ex. « Noël », « Louange »),
        pour regrouper et filtrer le répertoire selon le thème d'un culte.
        """
        mdc = membre_factory(chorale_a)
        mandat_factory(mdc, "maitre_choeur")
        client = auth_client(mdc)

        noel = client.post("/api/musique/themes/", {"nom": "Noël"}, format="json")
        louange = client.post("/api/musique/themes/", {"nom": "Louange"}, format="json")
        assert noel.status_code == 201 and louange.status_code == 201

        chant_noel = client.post(
            "/api/musique/chants/",
            {"titre": "Douce nuit", "style": "traditionnel", "themes_ids": [noel.data["id"]]},
            format="json",
        )
        assert chant_noel.status_code == 201, chant_noel.data
        assert chant_noel.data["themes"][0]["nom"] == "Noël"

        client.post(
            "/api/musique/chants/",
            {"titre": "Gloire à Dieu", "style": "gospel", "themes_ids": [louange.data["id"]]},
            format="json",
        )

        filtre = client.get(f"/api/musique/chants/?themes={noel.data['id']}")
        assert filtre.status_code == 200
        assert filtre.data["count"] == 1
        assert filtre.data["results"][0]["titre"] == "Douce nuit"

    def test_upload_partition_et_suivi_apprentissage(
        self, auth_client, membre_factory, mandat_factory, chorale_a, settings, tmp_path
    ):
        """3.1/3.2 : upload d'une partition + statut d'apprentissage par séance."""
        settings.MEDIA_ROOT = str(tmp_path)
        from django.core.files.uploadedfile import SimpleUploadedFile
        from presences.models import Repetition

        mdc = membre_factory(chorale_a)
        mandat_factory(mdc, "maitre_choeur")
        client = auth_client(mdc)

        chant = client.post(
            "/api/musique/chants/",
            {"titre": "Alleluia", "style": "gospel"}, format="json",
        ).data

        fichier = SimpleUploadedFile("score.pdf", b"%PDF-1.4 faux", content_type="application/pdf")
        up = client.post(
            "/api/musique/partitions/",
            {"chant": chant["id"], "titre": "Score complet", "fichier": fichier},
            format="multipart",
        )
        assert up.status_code == 201, up.data

        rep = Repetition.objects.create(chorale=chorale_a, date="2026-08-01", heure_debut="19:00")
        sc = client.post(
            "/api/musique/seances-chants/",
            {"repetition": rep.pk, "chant": chant["id"], "statut": "maitrise"},
            format="json",
        )
        assert sc.status_code == 201, sc.data

        detail = client.get(f"/api/musique/chants/{chant['id']}/").data
        assert detail["dernier_statut"] == "maitrise"
        assert detail["partitions"][0]["titre"] == "Score complet"


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

    def test_generer_puis_payer_cotisation(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """
        Flux 4.2 : générer les cotisations pour les membres actifs, puis
        enregistrer un paiement complet → statut « payé » + mouvement de caisse.
        """
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        membre_factory(chorale_a)  # 2e membre actif
        client = auth_client(tresorier)

        camp = client.post(
            "/api/finances/campagnes/",
            {"nom": "Annuelle 2026", "type_campagne": "annuelle",
             "montant_unitaire": "40.00", "date_debut": "2026-01-01"},
            format="json",
        ).data

        gen = client.post(f"/api/finances/campagnes/{camp['id']}/generer/")
        assert gen.status_code == 201
        assert gen.data["nombre"] == 2  # deux membres actifs

        cotisations = client.get(f"/api/finances/cotisations/?campagne={camp['id']}").data["results"]
        cot = cotisations[0]

        pay = client.post(
            "/api/finances/paiements/",
            {"cotisation": cot["id"], "montant": "40.00", "date_paiement": "2026-07-10"},
            format="json",
        )
        assert pay.status_code == 201, pay.data

        # La cotisation est soldée et un mouvement d'entrée a été créé.
        refreshed = client.get(f"/api/finances/cotisations/?campagne={camp['id']}").data["results"]
        payee = next(c for c in refreshed if c["id"] == cot["id"])
        assert payee["statut"] == "paye"
        mouvements = client.get("/api/finances/mouvements/?sens=entree").data
        assert mouvements["count"] >= 1

    def test_membre_voit_uniquement_ses_cotisations(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """Un membre lambda accède à SES cotisations (200) mais pas à celles des autres."""
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        m1 = membre_factory(chorale_a)
        membre_factory(chorale_a)  # m2, actif
        client_t = auth_client(tresorier)
        camp = client_t.post(
            "/api/finances/campagnes/",
            {"nom": "C", "type_campagne": "annuelle", "montant_unitaire": "10.00", "date_debut": "2026-01-01"},
            format="json",
        ).data
        client_t.post(f"/api/finances/campagnes/{camp['id']}/generer/")

        liste = auth_client(m1).get("/api/finances/cotisations/")
        assert liste.status_code == 200
        assert all(c["membre"] == m1.pk for c in liste.data["results"])

    def test_bulk_exonerer_et_bulk_encaisser_cotisations(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """Actions groupées serveur : un seul appel HTTP pour N cotisations."""
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        m1 = membre_factory(chorale_a); m2 = membre_factory(chorale_a); m3 = membre_factory(chorale_a)
        client = auth_client(tresorier)

        camp = client.post(
            "/api/finances/campagnes/",
            {"nom": "Bulk", "type_campagne": "annuelle", "montant_unitaire": "10.00", "date_debut": "2026-01-01"},
            format="json",
        ).data
        client.post(f"/api/finances/campagnes/{camp['id']}/generer/")
        cots = client.get(f"/api/finances/cotisations/?campagne={camp['id']}").data["results"]
        ids = [c["id"] for c in cots]

        exo = client.post("/api/finances/cotisations/bulk-exonerer/", {"ids": ids[:1]}, format="json")
        assert exo.status_code == 200
        assert exo.data["count"] == 1

        encaisse = client.post("/api/finances/cotisations/bulk-encaisser/", {"ids": ids[1:]}, format="json")
        assert encaisse.status_code == 200
        assert encaisse.data["count"] == len(ids) - 1

        refreshed = {c["id"]: c for c in client.get(f"/api/finances/cotisations/?campagne={camp['id']}").data["results"]}
        assert refreshed[ids[0]]["statut"] == "exonere"
        for i in ids[1:]:
            assert refreshed[i]["statut"] == "paye"

        # Un mouvement de caisse créé par cotisation encaissée.
        mvts = client.get("/api/finances/mouvements/?sens=entree").data
        assert mvts["count"] >= len(ids) - 1

    def test_bulk_approuver_permissions(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """Approbation groupée : demandes déjà traitées ignorées, pas bloquantes."""
        mdc = membre_factory(chorale_a)
        mandat_factory(mdc, "maitre_choeur")
        m1 = membre_factory(chorale_a); m2 = membre_factory(chorale_a)
        c1, c2 = auth_client(m1), auth_client(m2)
        d1 = c1.post("/api/presences/permissions/", {"date_debut": "2026-08-01", "date_fin": "2026-08-02", "motif": "x"}, format="json").data
        d2 = c2.post("/api/presences/permissions/", {"date_debut": "2026-08-03", "date_fin": "2026-08-04", "motif": "y"}, format="json").data

        client_mdc = auth_client(mdc)
        resp = client_mdc.post(
            "/api/presences/permissions/bulk-approuver/", {"ids": [d1["id"], d2["id"]]}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 2

        # Rejouer sur les mêmes ids : déjà traitées → 0, pas d'erreur.
        replay = client_mdc.post(
            "/api/presences/permissions/bulk-approuver/", {"ids": [d1["id"], d2["id"]]}, format="json"
        )
        assert replay.status_code == 200
        assert replay.data["count"] == 0

    def test_tarifs_par_sexe_appliques_a_la_generation(
        self, auth_client, membre_factory, mandat_factory, chorale_a
    ):
        """
        Décision retenue : des paliers (tarifs) par critère (sexe) fixent le
        montant dû à la génération — ex. Femmes 5000 / Hommes 4500.
        """
        tresorier = membre_factory(chorale_a)
        mandat_factory(tresorier, "tresorier")
        femme = membre_factory(chorale_a)
        femme.sexe = "femme"; femme.save(update_fields=["sexe"])
        homme = membre_factory(chorale_a)
        homme.sexe = "homme"; homme.save(update_fields=["sexe"])
        client = auth_client(tresorier)

        camp = client.post(
            "/api/finances/campagnes/",
            {"nom": "Tenues 2026", "type_campagne": "ponctuelle",
             "montant_unitaire": "5000.00", "date_debut": "2026-01-01"},
            format="json",
        ).data

        for sexe, montant in (("femme", "5000.00"), ("homme", "4500.00")):
            r = client.post(
                "/api/finances/tarifs/",
                {"campagne": camp["id"], "nom": f"Tenue {sexe}",
                 "montant": montant, "critere_sexe": sexe},
                format="json",
            )
            assert r.status_code == 201, r.data

        client.post(f"/api/finances/campagnes/{camp['id']}/generer/")
        cotisations = client.get(f"/api/finances/cotisations/?campagne={camp['id']}").data["results"]
        montants = {c["membre"]: c["montant_du"] for c in cotisations}
        assert montants[femme.pk] == "5000.00"
        assert montants[homme.pk] == "4500.00"
        # Tresorier sans sexe → tarif par défaut absent → montant_unitaire.
        assert montants[tresorier.pk] == "5000.00"

        # Montant éditable individuellement + exonération.
        cot_homme = next(c for c in cotisations if c["membre"] == homme.pk)
        patch = client.patch(
            f"/api/finances/cotisations/{cot_homme['id']}/",
            {"montant_du": "2250.00"}, format="json",
        )
        assert patch.status_code == 200
        assert patch.data["montant_du"] == "2250.00"

        exo = client.post(f"/api/finances/cotisations/{cot_homme['id']}/exonerer/")
        assert exo.status_code == 200
        assert exo.data["statut"] == "exonere"
