"""
ChoirManager — Rapports (exports PDF / CSV)
=============================================
Sépare volontairement trois étapes pour rester testable même là où les
libs natives de WeasyPrint (GTK/Pango/Cairo) ne sont pas installées :

    rendu_html(...)   → chaîne HTML (Django template)     [testable partout]
    html_vers_pdf(...) → bytes PDF via WeasyPrint          [nécessite GTK]
    lignes_csv(...)   → lignes CSV d'un rapport            [testable partout]

Les vues appellent ces fonctions selon le paramètre ?format=.
"""

import csv
import io
import os
import sys
from datetime import date

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone


class PdfIndisponible(RuntimeError):
    """WeasyPrint n'a pas pu charger ses dépendances système (GTK/Pango/Cairo)."""


# Emplacements Windows usuels des DLL GTK (MSYS2). Sur Windows, les libs de
# WeasyPrint ne sont pas trouvées via le PATH classique : il faut les déclarer
# explicitement avec os.add_dll_directory. On tente WEASYPRINT_DLL_DIR (env)
# puis les chemins MSYS2 par défaut. Sans effet hors Windows.
_GTK_DLL_DIRS_WINDOWS = [
    r"C:\msys64\ucrt64\bin",
    r"C:\msys64\mingw64\bin",
    r"C:\Program Files\GTK3-Runtime Win64\bin",
]


def _preparer_dll_gtk() -> None:
    if sys.platform != "win32":
        return
    candidats = []
    depuis_env = os.environ.get("WEASYPRINT_DLL_DIR") or getattr(settings, "WEASYPRINT_DLL_DIR", None)
    if depuis_env:
        candidats.append(depuis_env)
    candidats.extend(_GTK_DLL_DIRS_WINDOWS)
    for chemin in candidats:
        if chemin and os.path.isdir(chemin):
            try:
                os.add_dll_directory(chemin)
            except OSError:
                continue


# Métadonnées d'affichage par rapport (titre + template).
_META = {
    "financier": {"titre": "Rapport financier", "template": "rapports/financier.html"},
    "presences": {"titre": "Rapport de présences", "template": "rapports/presences.html"},
    "effectifs": {"titre": "Rapport d'effectifs", "template": "rapports/effectifs.html"},
    "repertoire": {"titre": "Rapport de répertoire", "template": "rapports/repertoire.html"},
}


def _periode_texte(data: dict) -> str:
    periode = data.get("periode") or {}
    debut, fin = periode.get("debut"), periode.get("fin")
    if debut and fin:
        return f"Du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"
    if debut:
        return f"À partir du {debut:%d/%m/%Y}"
    if fin:
        return f"Jusqu'au {fin:%d/%m/%Y}"
    return ""


def rendu_html(nom_rapport: str, data: dict, chorale) -> str:
    meta = _META[nom_rapport]
    return render_to_string(meta["template"], {
        "data": data,
        "chorale_nom": chorale.nom,
        "devise": chorale.currency,
        "titre": meta["titre"],
        "periode_texte": _periode_texte(data),
        "genere_le": timezone.localtime().strftime("%d/%m/%Y à %H:%M"),
    })


def html_vers_pdf(html: str) -> bytes:
    """
    Convertit du HTML en PDF via WeasyPrint. Lève PdfIndisponible (au lieu
    d'un OSError brut) si les libs système ne sont pas chargeables, pour que
    la vue puisse répondre proprement plutôt que planter en 500.
    """
    _preparer_dll_gtk()
    try:
        from weasyprint import HTML
    except OSError as exc:  # libs GTK/Pango absentes
        raise PdfIndisponible(str(exc)) from exc
    try:
        return HTML(string=html).write_pdf()
    except OSError as exc:
        raise PdfIndisponible(str(exc)) from exc


def rapport_vers_pdf(nom_rapport: str, data: dict, chorale) -> bytes:
    return html_vers_pdf(rendu_html(nom_rapport, data, chorale))


# ---------------------------------------------------------------------------
# CSV — une mise en forme tabulaire par rapport (le plus utile : le détail)
# ---------------------------------------------------------------------------

def lignes_csv(nom_rapport: str, data: dict) -> list[list]:
    """Renvoie la liste des lignes (en-tête inclus) du CSV d'un rapport."""
    if nom_rapport == "financier":
        lignes = [["Section", "Libellé", "Montant"]]
        for e in data["entrees_par_categorie"]:
            lignes.append(["Entrée", e["categorie"], e["total"]])
        for s in data["sorties_par_categorie"]:
            lignes.append(["Sortie", s["categorie"], s["total"]])
        lignes.append(["Total", "Entrées", data["total_entrees"]])
        lignes.append(["Total", "Sorties", data["total_sorties"]])
        lignes.append(["Total", "Solde", data["solde"]])
        for c in data["campagnes"]:
            lignes.append(["Cotisation", c["nom"], c["collecte"]])
        return lignes

    if nom_rapport == "presences":
        lignes = [["Membre", "Pupitre", "Présents", "Retards", "Absents", "Permissions", "Total", "Taux (%)"]]
        for m in data["par_membre"]:
            lignes.append([
                m["membre"], m["pupitre"], m["presents"], m["retards"],
                m["absents"], m["permissions"], m["total"], m["taux"],
            ])
        return lignes

    if nom_rapport == "effectifs":
        lignes = [["Dimension", "Libellé", "Effectif"]]
        for p in data["par_pupitre"]:
            lignes.append(["Pupitre", p["pupitre"], p["count"]])
        for s in data["par_statut"]:
            lignes.append(["Statut", s["statut"], s["count"]])
        for s in data["par_sexe"]:
            lignes.append(["Sexe", s["sexe"], s["count"]])
        return lignes

    if nom_rapport == "repertoire":
        lignes = [["Dimension", "Libellé", "Chants"]]
        for s in data["par_statut"]:
            lignes.append(["Statut", s["statut"], s["count"]])
        for t in data["par_theme"]:
            lignes.append(["Thème", t["theme"], t["count"]])
        return lignes

    raise ValueError(f"Rapport inconnu : {nom_rapport}")


def rapport_vers_csv(nom_rapport: str, data: dict) -> str:
    buffer = io.StringIO()
    # BOM UTF-8 pour qu'Excel ouvre correctement les accents.
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";")
    for ligne in lignes_csv(nom_rapport, data):
        writer.writerow(ligne)
    return buffer.getvalue()


def nom_fichier(nom_rapport: str, extension: str) -> str:
    return f"rapport_{nom_rapport}_{date.today():%Y%m%d}.{extension}"
