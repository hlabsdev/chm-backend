"""
ChoirManager — Module Notifications (Modèles)
================================================
Notification in-app destinée à UN membre. Créées exclusivement par
`notifications/services.py` (jamais directement depuis une vue) — c'est
le service qui décide aussi d'envoyer ou non un email en parallèle.

Volontairement simple : pas de temps réel (websocket), le front
rafraîchit le compteur périodiquement. Pas de soft-delete : une
notification lue et ancienne peut être purgée sans perte métier.
"""

from django.db import models

from core.models import ChoraleOwnedModel


class Notification(ChoraleOwnedModel):
    """Notification in-app adressée à un membre précis."""

    class Type(models.TextChoices):
        PERMISSION = "permission", "Demande d'absence"
        MANDAT = "mandat", "Mandat / poste"
        ANNONCE = "annonce", "Annonce"
        COTISATION = "cotisation", "Cotisation"
        SYSTEME = "systeme", "Système"

    destinataire = models.ForeignKey(
        "membres.Membre",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Destinataire",
    )
    type_notification = models.CharField(
        max_length=20, choices=Type.choices, default=Type.SYSTEME,
        verbose_name="Type",
    )
    titre = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    lien = models.CharField(
        max_length=200, blank=True,
        help_text="Route frontend vers la ressource concernée. Ex : /presences/permissions",
    )
    lue = models.BooleanField(default=False, db_index=True, verbose_name="Lue")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"{self.titre} → {self.destinataire}"
