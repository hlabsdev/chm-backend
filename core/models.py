"""
ChoirManager — Core Models
===========================
Modèles de base et mixins abstraits réutilisés dans tous les modules.

Hiérarchie :
    TimeStampedModel        → created_at, updated_at
    └── Chorale             → Entité tenant de premier niveau
    └── ChoraleOwnedModel   → FK vers Chorale (abstrait)
        └── SoftDeleteModel → is_deleted, deleted_at (abstrait)
"""

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# TimeStampedModel — horodatage automatique
# ---------------------------------------------------------------------------

class TimeStampedModel(models.Model):
    """
    Mixin abstrait : ajoute created_at / updated_at automatiques.
    Hérité par tous les modèles du projet.
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification"
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Chorale — Entité racine (tenant de premier niveau)
# ---------------------------------------------------------------------------

class Chorale(TimeStampedModel):
    """
    Entité racine — chaque chorale gérée sur la plateforme.
    Tous les autres modèles métier sont scopés à une Chorale.

    Le champ `prefix` sert à générer les matricules des membres.
    Ex: prefix='LVO' → matricules LVO-0001, LVO-0002, etc.
    """
    nom = models.CharField(
        max_length=200, unique=True,
        verbose_name="Nom de la chorale"
    )
    prefix = models.CharField(
        max_length=5, unique=True,
        help_text="Préfixe pour les matricules membres. Ex: 'LVO' → LVO-0042"
    )
    description = models.TextField(blank=True)
    logo = models.ImageField(
        upload_to="chorales/logos/",
        blank=True, null=True,
        verbose_name="Logo"
    )
    date_creation = models.DateField(
        verbose_name="Date de fondation",
        help_text="Date de création/fondation de la chorale"
    )
    devise = models.CharField(
        max_length=200, blank=True,
        verbose_name="Devise / Motto"
    )
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=25, blank=True)
    adresse = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Désactiver pour suspendre une chorale sans supprimer ses données."
    )

    class Meta:
        ordering = ["nom"]
        verbose_name = "Chorale"
        verbose_name_plural = "Chorales"

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------------------
# ChoraleOwnedModel — Mixin d'appartenance à une Chorale
# ---------------------------------------------------------------------------

class ChoraleOwnedModel(TimeStampedModel):
    """
    Mixin abstrait — lie tout modèle à une Chorale.
    Hérité par Membre, Pupitre, Poste, Chant, Repetition, Mouvement, etc.

    Le related_name utilise %(class)s pour éviter les conflits :
    → Chorale.membres, Chorale.postes, Chorale.chants, etc.
    """
    chorale = models.ForeignKey(
        Chorale,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name="Chorale"
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# SoftDeleteQuerySet & SoftDeleteModel — Suppression logique
# ---------------------------------------------------------------------------

class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet personnalisé pour filtrer les éléments soft-deleted."""

    def alive(self):
        """Retourne uniquement les éléments non supprimés."""
        return self.filter(is_deleted=False)

    def dead(self):
        """Retourne uniquement les éléments supprimés."""
        return self.filter(is_deleted=True)


class SoftDeleteModel(ChoraleOwnedModel):
    """
    Mixin abstrait : soft-delete + appartenance chorale.
    Pour les modèles sensibles (Membre, Mouvement, Chant, Cotisation).

    Utilisation :
        instance.soft_delete()   → marque comme supprimé
        instance.restore()       → restaure
        Model.objects.alive()    → QuerySet sans les supprimés
        Model.objects.dead()     → QuerySet des supprimés uniquement
    """
    is_deleted = models.BooleanField(
        default=False, db_index=True,
        verbose_name="Supprimé",
        help_text="True = suppression logique, les données sont conservées."
    )
    deleted_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de suppression"
    )

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    @property
    def is_active_record(self) -> bool:
        """True si l'enregistrement n'est pas soft-deleted."""
        return not self.is_deleted

    def soft_delete(self) -> None:
        """Marque l'enregistrement comme supprimé sans l'effacer de la DB."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def restore(self) -> None:
        """Restaure un enregistrement soft-deleted."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
