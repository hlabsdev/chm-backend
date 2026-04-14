"""
ChoirManager — Module Membres & Structure
===========================================
Entités : Pupitre, Poste, Membre, Mandat.

Architecture RBAC :
    Poste.groupes (M2M) → Groupes Django
    Mandat (FK Membre + FK Poste) → Signal post_save → sync user.groups

Chaque modèle est scopé à une Chorale via les mixins core :
    - Pupitre, Poste  → ChoraleOwnedModel
    - Membre           → SoftDeleteModel (inclut ChoraleOwnedModel)
    - Mandat           → TimeStampedModel (chorale déduite via membre)
"""

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import ChoraleOwnedModel, SoftDeleteModel, SoftDeleteQuerySet, TimeStampedModel


# ---------------------------------------------------------------------------
# Pupitre — section vocale (Soprano, Alto, Ténor, Basse…)
# ---------------------------------------------------------------------------

class Pupitre(ChoraleOwnedModel):
    """
    Section vocale au sein d'une chorale.
    Chaque chorale définit ses propres pupitres.
    """
    class Categorie(models.TextChoices):
        SOPRANO = "soprano", "Soprano"
        MEZZO   = "mezzo",   "Mezzo-soprano"
        ALTO    = "alto",    "Alto"
        TENOR   = "tenor",   "Ténor"
        BARYTON = "baryton", "Baryton"
        BASSE   = "basse",   "Basse"
        AUTRE   = "autre",   "Autre"

    nom = models.CharField(max_length=60)
    categorie = models.CharField(
        max_length=20,
        choices=Categorie.choices,
        verbose_name="Catégorie vocale"
    )
    ordre = models.PositiveSmallIntegerField(
        default=0,
        help_text="Ordre d'affichage dans les listes (0 = premier)"
    )

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "Pupitre"
        verbose_name_plural = "Pupitres"
        unique_together = ["chorale", "nom"]

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------------------
# Poste — rôle organisationnel lié aux groupes Django (RBAC)
#
# Exemples : Président, Trésorier, Maître de chœur Principal,
#            Maître de chœur Suppléant, Chef de pupitre Soprano…
#
# Le champ `groupes` fait le pont entre les postes organisationnels
# et le système RBAC Django. Un signal post_save sur Mandat
# synchronise automatiquement les groupes d'un membre.
# ---------------------------------------------------------------------------

class Poste(ChoraleOwnedModel):
    """
    Rôle organisationnel au sein de la chorale.
    Lié à des groupes Django pour le RBAC automatique via les Mandats.
    """
    class TypePoste(models.TextChoices):
        BUREAU    = "bureau",    "Bureau (élu)"
        DIRECTION = "direction", "Direction musicale"
        TECHNIQUE = "technique", "Technique / Organisation"
        AUTRE     = "autre",     "Autre"

    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    type_poste = models.CharField(
        max_length=20,
        choices=TypePoste.choices,
        verbose_name="Type de poste"
    )
    groupes = models.ManyToManyField(
        Group,
        blank=True,
        related_name="postes",
        help_text=(
            "Groupes Django accordés automatiquement "
            "lors d'un mandat actif sur ce poste."
        ),
    )
    pupitre_concerne = models.ForeignKey(
        Pupitre,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="postes_chef",
        help_text="À renseigner uniquement pour un poste de chef de pupitre.",
    )
    unique_actif = models.BooleanField(
        default=True,
        help_text=(
            "Si True, un seul titulaire actif à la fois. "
            "Mettre False pour les postes de suppléant."
        ),
    )

    class Meta:
        ordering = ["type_poste", "nom"]
        verbose_name = "Poste"
        verbose_name_plural = "Postes"
        unique_together = ["chorale", "nom"]

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------------------
# Membre — extension du User Django via OneToOneField
#
# Règle absolue : ne JAMAIS supprimer un Membre physiquement.
# Utiliser soft_delete() pour conserver l'historique des présences,
# des mandats et des mouvements financiers associés.
# ---------------------------------------------------------------------------

class MembreQuerySet(SoftDeleteQuerySet):
    """QuerySet personnalisé pour les Membres avec filtres métier."""

    def actifs(self):
        """Membres actifs et non soft-deleted."""
        return self.filter(statut=Membre.Statut.ACTIF, is_deleted=False)

    def par_pupitre(self, pupitre):
        """Filtre par pupitre."""
        return self.filter(pupitre=pupitre)

    def par_chorale(self, chorale):
        """Filtre par chorale."""
        return self.filter(chorale=chorale)


class Membre(SoftDeleteModel):
    """
    Profil chorale d'un utilisateur (séparé de User).

    User gère l'authentification (mot de passe, sessions, is_active).
    Membre porte le profil chorale (pupitre, statut, historique, chorale).
    """
    class Statut(models.TextChoices):
        ACTIF     = "actif",     "Actif"
        INACTIF   = "inactif",   "Inactif"
        HONORAIRE = "honoraire", "Honoraire"
        STAGIAIRE = "stagiaire", "Stagiaire"

    # --- Identité ---
    user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="membre",
        verbose_name="Utilisateur"
    )
    numero_membre = models.CharField(
        max_length=20, unique=True,
        verbose_name="Numéro de membre",
        help_text="Identifiant lisible auto-généré. Ex : LVO-0042"
    )
    date_adhesion = models.DateField(verbose_name="Date d'adhésion")
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.ACTIF,
    )

    # --- Section vocale ---
    pupitre = models.ForeignKey(
        Pupitre,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="membres",
    )

    # --- Contact ---
    telephone = models.CharField(max_length=25, blank=True)
    photo = models.ImageField(
        upload_to="membres/photos/",
        blank=True, null=True,
    )

    # --- Interne ---
    notes = models.TextField(
        blank=True,
        help_text="Notes internes — visibles Bureau et Admin uniquement.",
    )

    objects = MembreQuerySet.as_manager()

    class Meta:
        ordering = ["user__last_name", "user__first_name"]
        verbose_name = "Membre"
        verbose_name_plural = "Membres"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.numero_membre})"

    # --- Propriétés utilitaires ---

    @property
    def nom_complet(self) -> str:
        return self.user.get_full_name()

    @property
    def email(self) -> str:
        return self.user.email

    # --- Actions métier ---

    def soft_delete(self) -> None:
        """
        Désactive le compte sans effacer l'historique.
        - Passe le statut à INACTIF
        - Désactive le User Django
        - Clôture tous les mandats actifs (le signal retirera les groupes)
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.statut = self.Statut.INACTIF
        self.save(update_fields=["is_deleted", "deleted_at", "statut", "updated_at"])

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        # Clôturer tous les mandats actifs (le signal post_save retirera les groupes)
        self.mandats.filter(is_active=True).update(
            is_active=False,
            date_fin=timezone.now().date(),
        )

    def mandats_actifs(self):
        """Retourne les mandats actuellement en cours pour ce membre."""
        return self.mandats.filter(is_active=True).select_related("poste")

    # --- Génération du numéro de membre ---

    @classmethod
    def generer_numero(cls, chorale) -> str:
        """
        Génère le prochain numéro de membre pour une chorale donnée.
        Format : {PREFIX}-{XXXX}  ex: LVO-0042

        Le préfixe est tiré de chorale.prefix.

        NOTE : cette implémentation n'est pas thread-safe.
        En production avec trafic concurrent, utiliser une séquence
        PostgreSQL via django-sequences ou select_for_update().
        """
        last = (
            cls.objects
            .filter(chorale=chorale)
            .order_by("-id")
            .values("id")
            .first()
        )
        seq = (last["id"] + 1) if last else 1
        return f"{chorale.prefix}-{seq:04d}"


# ---------------------------------------------------------------------------
# Mandat — attribution temporelle d'un Poste à un Membre
#
# Un Mandat représente "Dupont a été Président du 01/01/2023 à aujourd'hui".
# C'est lui qui déclenche l'attribution/retrait des groupes Django via signal.
# ---------------------------------------------------------------------------

class Mandat(TimeStampedModel):
    """
    Attribution temporelle d'un poste à un membre.
    Le signal post_save synchronise les groupes Django automatiquement.
    """
    membre = models.ForeignKey(
        Membre,
        on_delete=models.PROTECT,
        related_name="mandats",
    )
    poste = models.ForeignKey(
        Poste,
        on_delete=models.PROTECT,
        related_name="mandats",
    )
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(
        null=True, blank=True,
        verbose_name="Date de fin",
        help_text="Laisser vide si le mandat est toujours en cours.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Mandat"
        verbose_name_plural = "Mandats"
        constraints = [
            # Un membre ne peut occuper le même poste qu'une seule fois simultanément
            models.UniqueConstraint(
                fields=["membre", "poste"],
                condition=models.Q(is_active=True),
                name="unique_mandat_actif_par_membre_poste",
            ),
        ]

    def __str__(self):
        etat = "en cours" if self.is_active else f"terminé {self.date_fin}"
        return f"{self.membre.nom_complet} — {self.poste} ({etat})"

    def clean(self):
        """
        Validation métier : si le poste n'accepte qu'un titulaire actif,
        vérifier qu'aucun autre mandat actif n'existe pour ce poste.
        """
        if self.is_active and getattr(self, "poste_id", None):
            if self.poste.unique_actif:
                conflit = (
                    Mandat.objects
                    .filter(poste=self.poste, is_active=True)
                    .exclude(pk=self.pk)
                    .select_related("membre")
                    .first()
                )
                if conflit:
                    raise ValidationError(
                        f"Le poste « {self.poste} » est déjà occupé par "
                        f"{conflit.membre.nom_complet}. Clôturez ce mandat "
                        f"avant d'en créer un nouveau."
                    )

    def terminer(self, date_fin=None) -> None:
        """
        Clôture proprement le mandat.
        Le signal post_save synchronise ensuite les groupes Django.
        """
        self.is_active = False
        self.date_fin = date_fin or timezone.now().date()
        self.save(update_fields=["is_active", "date_fin"])
