"""
Module Communications — Annonces
==================================
Couvre : publication réservée bureau/MDC, lecture ouverte à tout membre,
injection auteur/chorale côté serveur, filtrage des annonces expirées,
soft-delete, et isolation cross-tenant.
"""

import pytest

from communications.models import Annonce

pytestmark = pytest.mark.django_db

URL = "/api/communications/annonces/"


def test_bureau_joint_un_fichier_a_une_annonce(
    auth_client, membre_factory, mandat_factory, chorale_a, settings, tmp_path
):
    """La pièce jointe (la « lettre reçue ») doit pouvoir être uploadée."""
    settings.MEDIA_ROOT = str(tmp_path)
    from django.core.files.uploadedfile import SimpleUploadedFile

    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    fichier = SimpleUploadedFile("invitation.pdf", b"%PDF-1.4 lettre", content_type="application/pdf")

    resp = auth_client(bureau).post(
        URL,
        {"titre": "Invitation concert", "contenu": "Voir pièce jointe.", "piece_jointe": fichier},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["piece_jointe"]  # URL du fichier stocké


def test_bureau_publie_une_annonce_et_membre_la_lit(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    simple = membre_factory(chorale_a)

    resp = auth_client(bureau).post(
        URL,
        {"titre": "Concert de Noël", "contenu": "Invitation reçue pour un concert le 20/12."},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    # Auteur injecté côté serveur, jamais choisi par le client.
    assert resp.data["auteur"] == bureau.pk
    assert resp.data["auteur_nom"] == bureau.nom_complet

    liste = auth_client(simple).get(URL)
    assert liste.status_code == 200
    assert liste.data["count"] == 1
    assert liste.data["results"][0]["titre"] == "Concert de Noël"


def test_maitre_choeur_peut_aussi_publier(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    mdc = membre_factory(chorale_a)
    mandat_factory(mdc, "maitre_choeur")
    resp = auth_client(mdc).post(URL, {"titre": "Répét. exceptionnelle", "contenu": "Samedi 10h."}, format="json")
    assert resp.status_code == 201, resp.data


def test_membre_simple_ne_peut_pas_publier(auth_client, membre_factory, chorale_a):
    simple = membre_factory(chorale_a)
    resp = auth_client(simple).post(URL, {"titre": "X", "contenu": "Y"}, format="json")
    assert resp.status_code == 403


def test_annonce_expiree_masquee_par_defaut_mais_visible_sur_demande(
    auth_client, membre_factory, mandat_factory, chorale_a
):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    client = auth_client(bureau)

    Annonce.objects.create(
        chorale=chorale_a, auteur=bureau, titre="Passée", contenu="...",
        date_expiration="2020-01-01",
    )
    Annonce.objects.create(
        chorale=chorale_a, auteur=bureau, titre="Permanente", contenu="...",
    )

    fil = client.get(URL)
    titres = [a["titre"] for a in fil.data["results"]]
    assert "Permanente" in titres
    assert "Passée" not in titres

    complet = client.get(f"{URL}?inclure_expirees=true")
    titres_complet = [a["titre"] for a in complet.data["results"]]
    assert "Passée" in titres_complet
    assert complet.data["results"][[a["titre"] for a in complet.data["results"]].index("Passée")]["est_expiree"] is True


def test_epinglee_remonte_en_tete(auth_client, membre_factory, mandat_factory, chorale_a):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    Annonce.objects.create(chorale=chorale_a, auteur=bureau, titre="Normale", contenu="...")
    Annonce.objects.create(chorale=chorale_a, auteur=bureau, titre="Importante", contenu="...", epinglee=True)

    fil = auth_client(bureau).get(URL)
    assert fil.data["results"][0]["titre"] == "Importante"


def test_soft_delete_retire_du_fil(auth_client, membre_factory, mandat_factory, chorale_a):
    bureau = membre_factory(chorale_a)
    mandat_factory(bureau, "bureau")
    client = auth_client(bureau)
    annonce = Annonce.objects.create(chorale=chorale_a, auteur=bureau, titre="A supprimer", contenu="...")

    resp = client.delete(f"{URL}{annonce.pk}/")
    assert resp.status_code == 204
    annonce.refresh_from_db()
    assert annonce.is_deleted is True
    assert client.get(URL).data["count"] == 0


def test_isolation_annonce_de_b_invisible_pour_a(
    auth_client, membre_factory, mandat_factory, chorale_a, chorale_b
):
    bureau_b = membre_factory(chorale_b)
    mandat_factory(bureau_b, "bureau")
    annonce_b = Annonce.objects.create(chorale=chorale_b, auteur=bureau_b, titre="Interne B", contenu="...")

    bureau_a = membre_factory(chorale_a)
    mandat_factory(bureau_a, "bureau")
    client = auth_client(bureau_a)

    assert client.get(f"{URL}{annonce_b.pk}/").status_code == 404
    assert annonce_b.pk not in [a["id"] for a in client.get(URL).data["results"]]
