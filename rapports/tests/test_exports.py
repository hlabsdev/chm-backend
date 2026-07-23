"""
Module Rapports — exports PDF / CSV
=====================================
Le PDF (WeasyPrint) exige des libs système absentes de certains postes ;
on teste donc :
- le rendu HTML (source du PDF) sans dépendance native ;
- l'export CSV de bout en bout via l'API ;
- le câblage PDF via un mock (content-type / filename) ;
- la dégradation propre (503) quand WeasyPrint ne peut pas charger.
"""

import pytest

from rapports import exports, services
from rapports.templatetags.rapports_extras import montant

pytestmark = pytest.mark.django_db


@pytest.fixture
def bureau_a(membre_factory, mandat_factory, chorale_a):
    m = membre_factory(chorale_a)
    mandat_factory(m, "bureau")
    return m


def test_montant_formate_avec_separateur_de_milliers():
    # 1000 -> "1<insécable>000" ; le test ne dépend pas du caractère exact.
    formate = montant(1000)
    assert formate.startswith("1") and formate.endswith("000") and len(formate) == 5


def test_rendu_html_financier_contient_les_totaux(chorale_a, bureau_a, mouvement_factory):
    mouvement_factory(chorale_a, enregistre_par=bureau_a)  # entrée 1000
    data = services.rapport_financier(chorale_a)
    html = exports.rendu_html("financier", data, chorale_a)
    assert chorale_a.nom in html
    assert "Rapport financier" in html
    # Montant formaté (séparateur de milliers) présent dans le rendu.
    assert montant(1000) in html


def test_export_csv_presences_via_api(auth_client, bureau_a, membre_factory, chorale_a):
    from presences.models import Presence, Repetition
    choriste = membre_factory(chorale_a)
    rep = Repetition.objects.create(chorale=chorale_a, date="2026-01-05", heure_debut="19:00")
    Presence.objects.create(chorale=chorale_a, repetition=rep, membre=choriste, statut="present")

    resp = auth_client(bureau_a).get("/api/rapports/presences/?export=csv")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert "attachment" in resp["Content-Disposition"]
    assert ".csv" in resp["Content-Disposition"]
    corps = resp.content.decode("utf-8")
    assert "Membre" in corps
    assert choriste.nom_complet in corps


def test_export_csv_financier_lignes(chorale_a):
    data = services.rapport_financier(chorale_a)
    lignes = exports.lignes_csv("financier", data)
    assert lignes[0] == ["Section", "Libellé", "Montant"]


def test_export_pdf_cablage_via_mock(auth_client, bureau_a, monkeypatch):
    """Avec un moteur PDF simulé, l'API renvoie bien un application/pdf téléchargeable."""
    monkeypatch.setattr(exports, "html_vers_pdf", lambda html: b"%PDF-1.4 faux")
    resp = auth_client(bureau_a).get("/api/rapports/financier/?export=pdf")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert ".pdf" in resp["Content-Disposition"]
    assert resp.content == b"%PDF-1.4 faux"


def test_export_pdf_degrade_en_503_si_weasyprint_indisponible(auth_client, bureau_a, monkeypatch):
    def _boom(html):
        raise exports.PdfIndisponible("libgobject introuvable")
    monkeypatch.setattr(exports, "html_vers_pdf", _boom)

    resp = auth_client(bureau_a).get("/api/rapports/financier/?export=pdf")
    assert resp.status_code == 503
    assert "PDF" in resp.data["detail"]


def test_format_inconnu_retombe_sur_json(auth_client, bureau_a):
    resp = auth_client(bureau_a).get("/api/rapports/effectifs/?export=xml")
    assert resp.status_code == 200
    assert "total" in resp.data
