"""
ChoirManager — Module Présences (Modèles)
===========================================
Gestion des répétitions, du pointage des présences,
et des demandes de permission d'absence.
"""

from django.db import models

from core.models import ChoraleOwnedModel


class Repetition(ChoraleOwnedModel):
    """
    Séance de répétition de la chorale.
    Contient les métadonnées de la séance et le résumé.
    """
    date = models.DateField(verbose_name="Date de la répétition")
    heure_debut = models.TimeField(verbose_name="Heure de début")
    heure_fin = models.TimeField(
        null=True, blank=True,
        verbose_name="Heure de fin"
    )
    lieu = models.CharField(
        max_length=200, blank=True,
        verbose_name="Lieu"
    )
    resume = models.TextField(
        blank=True,
        verbose_name="Résumé de la séance",
        help_text="Ce qui a été travaillé, observations, décisions prises…"
    )
    dirigee_par = models.ForeignKey(
        "membres.Membre",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="repetitions_dirigees",
        verbose_name="Dirigée par"
    )

    class Meta:
        ordering = ["-date", "-heure_debut"]
        verbose_name = "Répétition"
        verbose_name_plural = "Répétitions"
        unique_together = ["chorale", "date", "heure_debut"]

    def __str__(self):
        return f"Répétition du {self.date} à {self.heure_debut}"

    @property
    def nombre_presents(self) -> int:
        """Nombre de membres présents à cette répétition."""
        return self.presences.filter(statut="present").count()

    @property
    def nombre_absents(self) -> int:
        """Nombre de membres absents à cette répétition."""
        return self.presences.filter(statut="absent").count()

    @property
    def taux_presence(self) -> float | None:
        """Pourcentage de présence. None si aucun pointage."""
        total = self.presences.count()
        if total == 0:
            return None
        presents = self.presences.filter(
            statut__in=["present", "retard"]
        ).count()
        return round(presents / total * 100, 1)


class Presence(ChoraleOwnedModel):
    """
    Pointage d'un membre à une répétition.
    Chaque membre a exactement un enregistrement par répétition.
    """
    class StatutPresence(models.TextChoices):
        PRESENT    = "present",    "Présent"
        ABSENT     = "absent",     "Absent"
        PERMISSION = "permission", "En permission"
        RETARD     = "retard",     "En retard"

    repetition = models.ForeignKey(
        Repetition,
        on_delete=models.CASCADE,
        related_name="presences",
    )
    membre = models.ForeignKey(
        "membres.Membre",
        on_delete=models.CASCADE,
        related_name="presences",
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutPresence.choices,
        verbose_name="Statut de présence"
    )
    motif = models.TextField(
        blank=True,
        help_text="Motif de l'absence ou du retard"
    )

    class Meta:
        ordering = ["membre__user__last_name"]
        verbose_name = "Présence"
        verbose_name_plural = "Présences"
        unique_together = ["repetition", "membre"]

    def __str__(self):
        return f"{self.membre.nom_complet} — {self.get_statut_display()}"


class PermissionRequest(ChoraleOwnedModel):
    """
    Demande d'absence anticipée soumise par un membre.
    Peut couvrir une ou plusieurs répétitions (plage de dates).
    """
    class StatutDemande(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        APPROUVEE  = "approuvee",  "Approuvée"
        REFUSEE    = "refusee",    "Refusée"

    membre = models.ForeignKey(
        "membres.Membre",
        on_delete=models.CASCADE,
        related_name="demandes_permission",
        verbose_name="Demandeur"
    )
    repetition = models.ForeignKey(
        Repetition,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="demandes_permission",
        help_text="Répétition spécifique concernée (optionnel si plage de dates)"
    )
    date_debut = models.DateField(verbose_name="Début de l'absence")
    date_fin = models.DateField(verbose_name="Fin de l'absence")
    motif = models.TextField(verbose_name="Motif de la demande")
    statut = models.CharField(
        max_length=20,
        choices=StatutDemande.choices,
        default=StatutDemande.EN_ATTENTE,
    )
    traitee_par = models.ForeignKey(
        "membres.Membre",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="permissions_traitees",
        verbose_name="Traitée par"
    )
    date_traitement = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de traitement"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de permission"
        verbose_name_plural = "Demandes de permission"

    def __str__(self):
        return f"{self.membre.nom_complet} — {self.date_debut} au {self.date_fin} ({self.get_statut_display()})"
