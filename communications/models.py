"""
ChoirManager — Module Communications (Modèles)
================================================
Annonces d'information de la chorale : une note diffusée à tous les
membres (ex. « une lettre d'invitation à un concert est arrivée »),
avec une trace conservée. Volontairement léger — pas de gestion
administrative verbeuse : ni accusés de lecture, ni notifications
push/email, ni catégories au départ.
"""

from django.db import models

from core.models import SoftDeleteModel


class Annonce(SoftDeleteModel):
    """
    Annonce diffusée aux membres d'une chorale.

    Soft-delete activé (comme toute donnée métier scopée chorale) pour
    conserver la trace d'une information passée. Une annonce peut être
    épinglée (mise en avant) et/ou dotée d'une date d'expiration après
    laquelle elle n'apparaît plus dans le fil actif.
    """
    titre = models.CharField(max_length=200, verbose_name="Titre")
    contenu = models.TextField(verbose_name="Contenu")
    auteur = models.ForeignKey(
        "membres.Membre",
        on_delete=models.PROTECT,
        related_name="annonces_publiees",
        verbose_name="Auteur",
        help_text="Membre (bureau ou maître de chœur) ayant publié l'annonce.",
    )
    piece_jointe = models.FileField(
        upload_to="annonces/%Y/%m/",
        blank=True, null=True,
        verbose_name="Pièce jointe",
        help_text="Document lié (lettre, affiche…). Optionnel.",
    )
    epinglee = models.BooleanField(
        default=False,
        verbose_name="Épinglée",
        help_text="Une annonce épinglée remonte en tête du fil.",
    )
    date_expiration = models.DateField(
        null=True, blank=True,
        verbose_name="Date d'expiration",
        help_text="Après cette date, l'annonce disparaît du fil actif. Vide = permanente.",
    )

    class Meta:
        # Épinglées d'abord, puis les plus récentes.
        ordering = ["-epinglee", "-created_at"]
        verbose_name = "Annonce"
        verbose_name_plural = "Annonces"

    def __str__(self):
        return self.titre
