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

    class Monnaie(models.TextChoices):
        XOF = "XOF", "Franc CFA — BCEAO (XOF)"
        XAF = "XAF", "Franc CFA — BEAC (XAF)"
        EUR = "EUR", "Euro (€)"
        USD = "USD", "Dollar US ($)"
        MAD = "MAD", "Dirham marocain (MAD)"
        GHS = "GHS", "Cedi ghanéen (GHS)"
        NGN = "NGN", "Naira nigérian (NGN)"

    currency = models.CharField(
        max_length=3,
        choices=Monnaie.choices,
        default=Monnaie.XOF,
        verbose_name="Monnaie de gestion",
        help_text="Devise utilisée pour toute la comptabilité de la chorale (défaut : Franc CFA XOF).",
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


# ---------------------------------------------------------------------------
# DemandeChorale — Demande publique d'adhésion d'une nouvelle chorale
# ---------------------------------------------------------------------------
#
# Volontairement PAS liée à une Chorale (elle en demande une nouvelle) et pas
# de provisionnement automatique : une demande reste `en_attente` jusqu'à
# modération humaine par l'opérateur (superuser, via l'admin Django), qui
# l'approuve — déclenchant `core.services.provisionner_chorale` — ou la
# rejette. C'est le rempart anti-abus : personne ne peut créer une chorale
# (et donc consommer des ressources / squatter un nom) sans revue humaine.

class DemandeChorale(TimeStampedModel):
    """Demande d'adhésion d'une nouvelle chorale à la plateforme (modérée)."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        APPROUVEE = "approuvee", "Approuvée"
        REJETEE = "rejetee", "Rejetée"

    # --- Renseigné par le demandeur (public, non authentifié) ---
    nom_chorale = models.CharField(max_length=200, verbose_name="Nom de la chorale souhaité")
    prefix_souhaite = models.CharField(
        max_length=5, blank=True,
        verbose_name="Préfixe souhaité",
        help_text="Suggestion du demandeur — l'opérateur confirme ou modifie le préfixe final.",
    )
    ville_pays = models.CharField(max_length=200, blank=True, verbose_name="Ville / Pays")
    contact_nom = models.CharField(max_length=200, verbose_name="Nom du contact")
    contact_email = models.EmailField(verbose_name="Email du contact")
    contact_telephone = models.CharField(max_length=25, blank=True)
    message = models.TextField(blank=True, verbose_name="Message / motivation")
    adresse_ip = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name="Adresse IP",
        help_text="Capturée pour l'audit anti-abus, jamais exposée publiquement.",
    )

    # --- Modération (opérateur, via l'admin Django) ---
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    prefix_attribue = models.CharField(
        max_length=5, blank=True,
        verbose_name="Préfixe attribué",
        help_text="À renseigner par l'opérateur avant d'approuver — devient le préfixe réel de la chorale.",
    )
    devise = models.CharField(
        max_length=3, choices=Chorale.Monnaie.choices, default=Chorale.Monnaie.XOF,
        verbose_name="Devise attribuée",
    )
    notes_internes = models.TextField(blank=True, verbose_name="Notes internes (non visibles du demandeur)")
    chorale_creee = models.ForeignKey(
        Chorale, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="demande_origine", verbose_name="Chorale créée",
    )
    date_traitement = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande d'adhésion chorale"
        verbose_name_plural = "Demandes d'adhésion chorale"

    def __str__(self):
        return f"{self.nom_chorale} — {self.get_statut_display()}"
