"""
ChoirManager — Module Musique (Modèles)
=========================================
Gestion du répertoire musical : Chants, Partitions, et suivi
de l'apprentissage par séance via SeanceChant.
"""

from django.db import models

from core.models import ChoraleOwnedModel, SoftDeleteModel


class Chant(SoftDeleteModel):
    """
    Morceau du répertoire de la chorale.
    Soft-delete activé pour conserver l'historique musical.
    """
    class Style(models.TextChoices):
        CLASSIQUE    = "classique",     "Classique"
        MODERNE      = "moderne",       "Moderne"
        TRADITIONNEL = "traditionnel",  "Traditionnel"
        GOSPEL       = "gospel",        "Gospel"
        LITURGIQUE   = "liturgique",    "Liturgique"
        AUTRE        = "autre",         "Autre"

    titre = models.CharField(max_length=200, verbose_name="Titre du chant")
    compositeur = models.CharField(max_length=200, blank=True, verbose_name="Compositeur / Auteur")
    style = models.CharField(
        max_length=20,
        choices=Style.choices,
        verbose_name="Genre / Style"
    )
    tonalite = models.CharField(
        max_length=10, blank=True,
        verbose_name="Tonalité",
        help_text="Ex: Do majeur, Si bémol mineur"
    )
    tempo = models.CharField(
        max_length=50, blank=True,
        help_text="Ex: Allegro, 120 BPM, Lent"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes sur le chant, consignes d'interprétation, etc."
    )

    class Meta:
        ordering = ["titre"]
        verbose_name = "Chant"
        verbose_name_plural = "Chants"
        unique_together = ["chorale", "titre", "compositeur"]

    def __str__(self):
        if self.compositeur:
            return f"{self.titre} — {self.compositeur}"
        return self.titre

    @property
    def nombre_partitions(self) -> int:
        return self.partitions.count()


class Partition(ChoraleOwnedModel):
    """
    Fichier de partition lié à un chant.
    Peut être associé à un pupitre spécifique (ex: partition Soprano).
    """
    chant = models.ForeignKey(
        Chant,
        on_delete=models.CASCADE,
        related_name="partitions",
    )
    titre = models.CharField(
        max_length=200,
        verbose_name="Titre du fichier",
        help_text="Ex: 'Partition Soprano', 'Score complet'"
    )
    fichier = models.FileField(
        upload_to="partitions/%Y/%m/",
        verbose_name="Fichier (PDF, image…)"
    )
    type_voix = models.ForeignKey(
        "membres.Pupitre",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="partitions",
        verbose_name="Pupitre concerné",
        help_text="Laisser vide si la partition est pour toutes les voix."
    )

    class Meta:
        ordering = ["chant__titre", "titre"]
        verbose_name = "Partition"
        verbose_name_plural = "Partitions"

    def __str__(self):
        return f"{self.chant.titre} — {self.titre}"


class SeanceChant(ChoraleOwnedModel):
    """
    Liaison Séance (Répétition) ↔ Chant avec statut d'apprentissage.
    Permet de suivre la progression : introduit → en travail → maîtrisé.

    Le répertoire actif se construit naturellement à partir de ces liaisons.
    """
    class StatutApprentissage(models.TextChoices):
        INTRODUIT  = "introduit",  "Introduit"
        EN_TRAVAIL = "en_travail", "En travail"
        MAITRISE   = "maitrise",   "Maîtrisé"

    repetition = models.ForeignKey(
        "presences.Repetition",
        on_delete=models.CASCADE,
        related_name="chants_travailles",
        verbose_name="Répétition"
    )
    chant = models.ForeignKey(
        Chant,
        on_delete=models.CASCADE,
        related_name="seances",
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutApprentissage.choices,
        default=StatutApprentissage.INTRODUIT,
        verbose_name="Statut d'apprentissage"
    )
    notes = models.TextField(
        blank=True,
        help_text="Observations sur la séance (difficultés, progrès…)"
    )

    class Meta:
        ordering = ["-repetition__date"]
        verbose_name = "Chant travaillé en séance"
        verbose_name_plural = "Chants travaillés en séance"
        unique_together = ["repetition", "chant"]

    def __str__(self):
        return f"{self.chant.titre} — {self.get_statut_display()}"
