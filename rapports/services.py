"""
ChoirManager — Rapports (agrégation)
======================================
Couche métier des rapports : chaque fonction prend une chorale (et
éventuellement une période) et renvoie un dict prêt à sérialiser en JSON,
à rendre en PDF ou à exporter en CSV. Aucune logique de présentation ici.

Toutes les requêtes sont scopées à la chorale passée en argument — jamais
de fuite cross-tenant. Les montants Decimal sont convertis en str par le
serializer/exporteur en aval ; ici on reste en Decimal pour l'exactitude.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Sum

from finances.models import CampagneCotisation, Mouvement
from membres.models import Membre, Pupitre
from musique.models import Chant, Theme
from presences.models import Presence, Repetition

# Ordre vocal canonique (cf. shared côté front) — pour trier les regroupements
# par pupitre de façon cohérente dans toute l'appli.
_ORDRE_CATEGORIE = {
    "soprano": 1, "mezzo": 2, "alto": 3,
    "tenor": 4, "baryton": 5, "basse": 6, "autre": 7,
}


def _rang_pupitre(pupitre: Pupitre) -> int:
    return _ORDRE_CATEGORIE.get(pupitre.categorie, 99)


# ---------------------------------------------------------------------------
# Rapport financier
# ---------------------------------------------------------------------------

def rapport_financier(chorale, date_debut: date | None = None, date_fin: date | None = None) -> dict:
    """État de caisse sur une période + état des cotisations par campagne."""
    mouvements = Mouvement.objects.filter(chorale=chorale, is_deleted=False)
    if date_debut:
        mouvements = mouvements.filter(date__gte=date_debut)
    if date_fin:
        mouvements = mouvements.filter(date__lte=date_fin)

    entrees_par_cat = (
        mouvements.filter(sens=Mouvement.Sens.ENTREE)
        .values("categorie__nom")
        .annotate(total=Sum("montant"))
        .order_by("-total")
    )
    sorties_par_cat = (
        mouvements.filter(sens=Mouvement.Sens.SORTIE)
        .values("categorie__nom")
        .annotate(total=Sum("montant"))
        .order_by("-total")
    )
    total_entrees = mouvements.filter(sens=Mouvement.Sens.ENTREE).aggregate(t=Sum("montant"))["t"] or Decimal("0")
    total_sorties = mouvements.filter(sens=Mouvement.Sens.SORTIE).aggregate(t=Sum("montant"))["t"] or Decimal("0")

    # Cotisations par campagne (recouvrement). Non borné par la période :
    # une campagne a sa propre temporalité, on donne son état courant.
    campagnes = []
    for camp in CampagneCotisation.objects.filter(chorale=chorale).order_by("-date_debut"):
        attendu = camp.montant_total_attendu or Decimal("0")
        collecte = camp.montant_total_collecte or Decimal("0")
        campagnes.append({
            "nom": camp.nom,
            "type": camp.get_type_campagne_display(),
            "attendu": attendu,
            "collecte": collecte,
            "restant": max(attendu - collecte, Decimal("0")),
            "taux_recouvrement": camp.taux_recouvrement,
        })

    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "entrees_par_categorie": [
            {"categorie": e["categorie__nom"], "total": e["total"]} for e in entrees_par_cat
        ],
        "sorties_par_categorie": [
            {"categorie": s["categorie__nom"], "total": s["total"]} for s in sorties_par_cat
        ],
        "total_entrees": total_entrees,
        "total_sorties": total_sorties,
        "solde": total_entrees - total_sorties,
        "nombre_mouvements": mouvements.count(),
        "campagnes": campagnes,
    }


# ---------------------------------------------------------------------------
# Rapport de présences
# ---------------------------------------------------------------------------

def rapport_presences(chorale, date_debut: date | None = None, date_fin: date | None = None) -> dict:
    """Assiduité sur une période : taux global, par pupitre, par membre."""
    repetitions = Repetition.objects.filter(chorale=chorale)
    if date_debut:
        repetitions = repetitions.filter(date__gte=date_debut)
    if date_fin:
        repetitions = repetitions.filter(date__lte=date_fin)
    rep_ids = list(repetitions.values_list("id", flat=True))

    presences = Presence.objects.filter(chorale=chorale, repetition_id__in=rep_ids)
    total_pointages = presences.count()
    total_ok = presences.filter(statut__in=["present", "retard"]).count()
    taux_global = round(total_ok / total_pointages * 100, 1) if total_pointages else None

    # Par membre.
    par_membre = []
    membres = (
        Membre.objects.filter(chorale=chorale, is_deleted=False)
        .select_related("user", "pupitre")
    )
    for m in membres:
        p = presences.filter(membre=m)
        total = p.count()
        if total == 0:
            continue
        presents = p.filter(statut="present").count()
        retards = p.filter(statut="retard").count()
        absents = p.filter(statut="absent").count()
        permissions = p.filter(statut="permission").count()
        par_membre.append({
            "membre": m.nom_complet,
            "pupitre": m.pupitre.nom if m.pupitre_id else "—",
            "_rang": _rang_pupitre(m.pupitre) if m.pupitre_id else 99,
            "presents": presents,
            "retards": retards,
            "absents": absents,
            "permissions": permissions,
            "total": total,
            "taux": round((presents + retards) / total * 100, 1),
        })
    par_membre.sort(key=lambda x: (x["_rang"], -x["taux"]))
    for row in par_membre:
        row.pop("_rang")

    # Par pupitre (agrégat).
    par_pupitre = []
    for pupitre in sorted(Pupitre.objects.filter(chorale=chorale), key=_rang_pupitre):
        p = presences.filter(membre__pupitre=pupitre)
        total = p.count()
        if total == 0:
            continue
        ok = p.filter(statut__in=["present", "retard"]).count()
        par_pupitre.append({
            "pupitre": pupitre.nom,
            "total": total,
            "presents_retards": ok,
            "taux": round(ok / total * 100, 1),
        })

    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_repetitions": len(rep_ids),
        "taux_global": taux_global,
        "par_pupitre": par_pupitre,
        "par_membre": par_membre,
    }


# ---------------------------------------------------------------------------
# Rapport d'effectifs
# ---------------------------------------------------------------------------

def rapport_effectifs(chorale) -> dict:
    """Photographie des membres : par pupitre, par statut, par sexe."""
    membres = Membre.objects.filter(chorale=chorale, is_deleted=False)
    total = membres.count()

    par_pupitre = []
    for pupitre in sorted(Pupitre.objects.filter(chorale=chorale), key=_rang_pupitre):
        par_pupitre.append({
            "pupitre": pupitre.nom,
            "count": membres.filter(pupitre=pupitre).count(),
        })
    sans_pupitre = membres.filter(pupitre__isnull=True).count()
    if sans_pupitre:
        par_pupitre.append({"pupitre": "Sans pupitre", "count": sans_pupitre})

    par_statut = [
        {"statut": libelle, "count": membres.filter(statut=valeur).count()}
        for valeur, libelle in Membre.Statut.choices
    ]
    par_sexe = [
        {"sexe": libelle, "count": membres.filter(sexe=valeur).count()}
        for valeur, libelle in Membre.Sexe.choices
    ]
    sexe_non_renseigne = membres.filter(sexe="").count()
    if sexe_non_renseigne:
        par_sexe.append({"sexe": "Non renseigné", "count": sexe_non_renseigne})

    return {
        "total": total,
        "par_pupitre": par_pupitre,
        "par_statut": par_statut,
        "par_sexe": par_sexe,
    }


# ---------------------------------------------------------------------------
# Rapport de répertoire
# ---------------------------------------------------------------------------

def rapport_repertoire(chorale) -> dict:
    """État du répertoire : chants par dernier statut d'apprentissage, par thème."""
    chants = Chant.objects.filter(chorale=chorale, is_deleted=False)
    total = chants.count()

    # Dernier statut d'apprentissage par chant (via la séance la plus récente).
    compte_statuts = {"introduit": 0, "en_travail": 0, "maitrise": 0, "aucun": 0}
    for chant in chants.prefetch_related("seances"):
        dernier = (
            chant.seances.order_by("-repetition__date")
            .values_list("statut", flat=True)
            .first()
        )
        compte_statuts[dernier if dernier else "aucun"] += 1

    par_statut = [
        {"statut": "Maîtrisé", "count": compte_statuts["maitrise"]},
        {"statut": "En travail", "count": compte_statuts["en_travail"]},
        {"statut": "Introduit", "count": compte_statuts["introduit"]},
        {"statut": "Jamais travaillé", "count": compte_statuts["aucun"]},
    ]

    par_theme = [
        {"theme": t.nom, "count": c}
        for t, c in sorted(
            ((t, t.chants.filter(is_deleted=False).count()) for t in Theme.objects.filter(chorale=chorale)),
            key=lambda x: -x[1],
        )
    ]

    return {
        "total": total,
        "par_statut": par_statut,
        "par_theme": par_theme,
    }
