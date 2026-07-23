"""
ChoirManager — Module Finances (Modèles)
==========================================
Journal de caisse, campagnes de cotisation, suivi des paiements.

Architecture :
    CampagneCotisation  →  le POURQUOI (uniforme, mensuelle, sortie…)
    Cotisation           →  l'attribution à un membre + suivi paiement
    PaiementCotisation  →  chaque paiement individuel (permet les partiels)
    Mouvement           →  ligne du journal de caisse (toute entrée/sortie)
"""

from django.db import models

from core.models import ChoraleOwnedModel, SoftDeleteModel, TimeStampedModel


# ---------------------------------------------------------------------------
# Catégories de mouvement
# ---------------------------------------------------------------------------

class CategorieMouvement(ChoraleOwnedModel):
    """
    Catégorie de mouvement financier.
    Exemples : Cotisation, Don, Achat matériel, Location salle, Transport…
    """
    class TypeMouvement(models.TextChoices):
        ENTREE = "entree", "Entrée"
        SORTIE = "sortie", "Sortie"

    nom = models.CharField(max_length=100, verbose_name="Nom de la catégorie")
    type_mouvement = models.CharField(
        max_length=10,
        choices=TypeMouvement.choices,
        verbose_name="Type"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["type_mouvement", "nom"]
        unique_together = ["chorale", "nom"]
        verbose_name = "Catégorie de mouvement"
        verbose_name_plural = "Catégories de mouvement"

    def __str__(self):
        return f"{self.nom} ({self.get_type_mouvement_display()})"


# ---------------------------------------------------------------------------
# Mouvement — ligne du journal de caisse
# ---------------------------------------------------------------------------

class Mouvement(SoftDeleteModel):
    """
    Ligne du journal de caisse — chaque entrée ou sortie d'argent.
    Soft-delete activé pour l'intégrité financière.
    """
    class Sens(models.TextChoices):
        ENTREE = "entree", "Entrée"
        SORTIE = "sortie", "Sortie"

    date = models.DateField(verbose_name="Date du mouvement")
    montant = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name="Montant"
    )
    sens = models.CharField(
        max_length=10,
        choices=Sens.choices,
        verbose_name="Sens"
    )
    categorie = models.ForeignKey(
        CategorieMouvement,
        on_delete=models.PROTECT,
        related_name="mouvements",
        verbose_name="Catégorie"
    )
    motif = models.CharField(
        max_length=300,
        verbose_name="Motif / Libellé"
    )
    membre = models.ForeignKey(
        "membres.Membre",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="mouvements",
        verbose_name="Membre concerné",
        help_text="Membre lié au mouvement (paiement cotisation, don nominatif…)"
    )
    enregistre_par = models.ForeignKey(
        "membres.Membre",
        on_delete=models.PROTECT,
        related_name="mouvements_enregistres",
        verbose_name="Enregistré par"
    )
    piece_jointe = models.FileField(
        upload_to="finances/%Y/%m/",
        blank=True,
        verbose_name="Pièce justificative"
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Mouvement financier"
        verbose_name_plural = "Mouvements financiers"

    def __str__(self):
        signe = "+" if self.sens == self.Sens.ENTREE else "-"
        return f"{self.date} | {signe}{self.montant} | {self.motif}"


# ---------------------------------------------------------------------------
# Campagne de cotisation — le POURQUOI
# ---------------------------------------------------------------------------

class CampagneCotisation(ChoraleOwnedModel):
    """
    Définition d'une cotisation — le motif concret.

    Exemples :
      - "Cotisation mensuelle — Janvier 2025"  (type=mensuelle)
      - "Confection uniforme 2025"             (type=ponctuelle)
      - "Sortie détente Kribi"                 (type=evenementielle)
      - "Cotisation annuelle 2025"             (type=annuelle)

    Le champ montant_unitaire définit le montant attendu par membre.
    is_obligatoire détermine si tous les membres actifs doivent payer.
    """
    class TypeCampagne(models.TextChoices):
        MENSUELLE      = "mensuelle",      "Mensuelle"
        ANNUELLE       = "annuelle",       "Annuelle"
        PONCTUELLE     = "ponctuelle",     "Ponctuelle"
        EVENEMENTIELLE = "evenementielle", "Événementielle"

    nom = models.CharField(max_length=200, verbose_name="Nom de la campagne")
    description = models.TextField(blank=True)
    type_campagne = models.CharField(
        max_length=20,
        choices=TypeCampagne.choices,
        verbose_name="Type"
    )
    montant_unitaire = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Montant par membre",
        help_text="Montant attendu de chaque membre concerné"
    )
    date_debut = models.DateField(
        verbose_name="Début de la collecte"
    )
    date_fin = models.DateField(
        null=True, blank=True,
        verbose_name="Date limite",
        help_text="Laisser vide si pas de deadline"
    )
    is_obligatoire = models.BooleanField(
        default=True,
        verbose_name="Obligatoire",
        help_text="Si True, génère automatiquement une cotisation pour chaque membre actif"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active"
    )

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Campagne de cotisation"
        verbose_name_plural = "Campagnes de cotisation"

    def __str__(self):
        return f"{self.nom} ({self.get_type_campagne_display()})"

    @property
    def montant_total_attendu(self):
        """Montant total attendu pour cette campagne."""
        return self.cotisations.aggregate(
            total=models.Sum("montant_du")
        )["total"] or 0

    @property
    def montant_total_collecte(self):
        """Montant total effectivement collecté."""
        return self.cotisations.aggregate(
            total=models.Sum("montant_paye")
        )["total"] or 0

    @property
    def taux_recouvrement(self):
        """Pourcentage de recouvrement."""
        attendu = self.montant_total_attendu
        if attendu == 0:
            return 0
        return round(float(self.montant_total_collecte / attendu) * 100, 1)

    def montant_pour(self, membre):
        """
        Montant dû par un membre selon les paliers (tarifs) de la campagne :
        tarif par sexe > tarif par pupitre > tarif par défaut > montant_unitaire.
        """
        tarifs = list(self.tarifs.all())
        for t in tarifs:
            if t.critere_sexe and not t.critere_pupitre_id and t.correspond(membre):
                return t.montant
        for t in tarifs:
            if t.critere_pupitre_id and t.correspond(membre):
                return t.montant
        for t in tarifs:
            if t.est_defaut:
                return t.montant
        return self.montant_unitaire


# ---------------------------------------------------------------------------
# TarifCotisation — palier de montant au sein d'une campagne
#
# Permet des montants différents selon un critère de membre (sexe, pupitre).
# Ex. « Tenue femmes : 5000 » / « Tenue hommes : 4500 ».
# Un tarif sans critère sert de tarif PAR DÉFAUT (fallback).
# Le montant reste éditable individuellement sur chaque Cotisation ensuite.
# ---------------------------------------------------------------------------

class TarifCotisation(ChoraleOwnedModel):
    """Palier de cotisation appliqué selon un critère de membre."""
    campagne = models.ForeignKey(
        CampagneCotisation,
        on_delete=models.CASCADE,
        related_name="tarifs",
    )
    nom = models.CharField(max_length=100, verbose_name="Libellé du tarif")
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    critere_sexe = models.CharField(
        max_length=10, blank=True,
        verbose_name="Critère sexe",
        help_text="Si renseigné, ce tarif s'applique aux membres de ce sexe.",
    )
    critere_pupitre = models.ForeignKey(
        "membres.Pupitre",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="tarifs_cotisation",
        verbose_name="Critère pupitre",
        help_text="Si renseigné, ce tarif s'applique aux membres de ce pupitre.",
    )

    class Meta:
        ordering = ["campagne", "nom"]
        verbose_name = "Tarif de cotisation"
        verbose_name_plural = "Tarifs de cotisation"

    def __str__(self):
        return f"{self.nom} — {self.montant}"

    def correspond(self, membre) -> bool:
        """True si ce tarif s'applique au membre selon ses critères."""
        if self.critere_sexe and membre.sexe != self.critere_sexe:
            return False
        if self.critere_pupitre_id and membre.pupitre_id != self.critere_pupitre_id:
            return False
        return True

    @property
    def est_defaut(self) -> bool:
        return not self.critere_sexe and not self.critere_pupitre_id


# ---------------------------------------------------------------------------
# Cotisation — attribution d'une campagne à un membre
# ---------------------------------------------------------------------------

class Cotisation(SoftDeleteModel):
    """
    Attribution d'une campagne de cotisation à un membre.
    Suit le montant dû, le montant payé, et le statut.

    Une cotisation peut être payée en plusieurs fois via PaiementCotisation.
    """
    class StatutCotisation(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        PARTIEL    = "partiel",    "Partiel"
        PAYE       = "paye",       "Payé"
        EXONERE    = "exonere",    "Exonéré"

    campagne = models.ForeignKey(
        CampagneCotisation,
        on_delete=models.CASCADE,
        related_name="cotisations",
        verbose_name="Campagne"
    )
    membre = models.ForeignKey(
        "membres.Membre",
        on_delete=models.CASCADE,
        related_name="cotisations",
    )
    montant_du = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Montant dû",
        help_text="Peut différer du montant_unitaire (exonération partielle)"
    )
    montant_paye = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0,
        verbose_name="Montant payé"
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutCotisation.choices,
        default=StatutCotisation.EN_ATTENTE,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-campagne__date_debut"]
        unique_together = ["campagne", "membre"]
        verbose_name = "Cotisation"
        verbose_name_plural = "Cotisations"

    def __str__(self):
        return f"{self.membre.nom_complet} — {self.campagne.nom} ({self.get_statut_display()})"

    @property
    def reste_a_payer(self):
        """Montant restant dû."""
        return max(self.montant_du - self.montant_paye, 0)

    @property
    def is_solde(self):
        """True si la cotisation est intégralement payée."""
        return self.montant_paye >= self.montant_du

    def recalculer_statut(self):
        """Recalcule le statut en fonction du montant payé."""
        if self.statut == self.StatutCotisation.EXONERE:
            return  # Ne pas toucher aux exonérations

        if self.montant_paye >= self.montant_du:
            self.statut = self.StatutCotisation.PAYE
        elif self.montant_paye > 0:
            self.statut = self.StatutCotisation.PARTIEL
        else:
            self.statut = self.StatutCotisation.EN_ATTENTE


# ---------------------------------------------------------------------------
# PaiementCotisation — trace de chaque paiement individuel
# ---------------------------------------------------------------------------

class PaiementCotisation(TimeStampedModel):
    """
    Trace chaque paiement individuel sur une cotisation.
    Permet les paiements partiels et l'historique complet.

    Chaque paiement est lié à un Mouvement dans le journal de caisse
    pour garantir la cohérence financière.
    """
    cotisation = models.ForeignKey(
        Cotisation,
        on_delete=models.CASCADE,
        related_name="paiements",
    )
    montant = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Montant payé"
    )
    date_paiement = models.DateField(verbose_name="Date du paiement")
    mouvement = models.OneToOneField(
        Mouvement,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="paiement_cotisation",
        verbose_name="Mouvement correspondant",
        help_text="Lien vers le mouvement dans le journal de caisse"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_paiement"]
        verbose_name = "Paiement de cotisation"
        verbose_name_plural = "Paiements de cotisation"

    def __str__(self):
        return (
            f"{self.cotisation.membre.nom_complet} — "
            f"{self.montant} le {self.date_paiement}"
        )
