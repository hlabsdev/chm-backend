"""
ChoirManager — Membres Serializers
====================================
Sérialiseurs DRF pour Pupitre, Poste, Membre, Mandat.
"""

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Mandat, Membre, Poste, Pupitre


# ---------------------------------------------------------------------------
# Pupitre
# ---------------------------------------------------------------------------

class PupitreSerializer(serializers.ModelSerializer):
    """Sérialiseur complet pour les pupitres."""
    nombre_membres = serializers.SerializerMethodField()

    class Meta:
        model = Pupitre
        fields = [
            "id", "nom", "categorie", "ordre",
            "nombre_membres", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_nombre_membres(self, obj) -> int:
        """Nombre de membres actifs dans ce pupitre."""
        return obj.membres.filter(is_deleted=False, statut="actif").count()


# ---------------------------------------------------------------------------
# Poste
# ---------------------------------------------------------------------------

class PosteSerializer(serializers.ModelSerializer):
    """Sérialiseur complet pour les postes."""
    groupes_noms = serializers.SlugRelatedField(
        source="groupes",
        many=True,
        read_only=True,
        slug_field="name",
    )
    titulaire_actuel = serializers.SerializerMethodField()

    class Meta:
        model = Poste
        fields = [
            "id", "nom", "description", "type_poste",
            "unique_actif", "pupitre_concerne",
            "groupes_noms", "titulaire_actuel",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_titulaire_actuel(self, obj) -> dict | None:
        """Retourne le titulaire actif du poste, si existant."""
        mandat = (
            obj.mandats
            .filter(is_active=True)
            .select_related("membre__user")
            .first()
        )
        if mandat:
            return {
                "membre_id": mandat.membre.pk,
                "nom_complet": mandat.membre.nom_complet,
                "depuis": mandat.date_debut,
            }
        return None


# ---------------------------------------------------------------------------
# Mandat
# ---------------------------------------------------------------------------

class MandatSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les mandats avec validation métier."""
    membre_nom = serializers.CharField(
        source="membre.nom_complet", read_only=True
    )
    poste_nom = serializers.CharField(
        source="poste.nom", read_only=True
    )

    class Meta:
        model = Mandat
        fields = [
            "id", "membre", "membre_nom",
            "poste", "poste_nom",
            "date_debut", "date_fin", "is_active",
            "notes", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        """Valide les contraintes métier (unique_actif, dates)."""
        poste = data.get("poste") or self.instance.poste if self.instance else None
        is_active = data.get("is_active", True)
        membre = data.get("membre") or self.instance.membre if self.instance else None

        if poste and is_active and poste.unique_actif:
            conflit = (
                Mandat.objects
                .filter(poste=poste, is_active=True)
                .exclude(pk=self.instance.pk if self.instance else None)
                .select_related("membre")
                .first()
            )
            if conflit:
                raise serializers.ValidationError(
                    f"Le poste « {poste.nom} » est déjà occupé par "
                    f"{conflit.membre.nom_complet}."
                )

        # Validation des dates
        date_debut = data.get("date_debut")
        date_fin = data.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({
                "date_fin": "La date de fin ne peut pas être antérieure à la date de début."
            })

        return data


class MandatNestedSerializer(serializers.ModelSerializer):
    """Sérialiseur imbriqué (lecture seule) pour afficher dans le détail d'un membre."""
    poste_nom = serializers.CharField(source="poste.nom", read_only=True)
    poste_type = serializers.CharField(source="poste.type_poste", read_only=True)

    class Meta:
        model = Mandat
        fields = [
            "id", "poste", "poste_nom", "poste_type",
            "date_debut", "date_fin", "is_active",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Membre
# ---------------------------------------------------------------------------

class MembreListSerializer(serializers.ModelSerializer):
    """
    Sérialiseur léger pour les listes de membres.
    Optimisé pour minimiser les requêtes DB.
    """
    nom_complet = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    pupitre_nom = serializers.CharField(source="pupitre.nom", read_only=True, default=None)

    class Meta:
        model = Membre
        fields = [
            "id", "numero_membre", "nom_complet", "email",
            "pupitre", "pupitre_nom", "statut",
            "date_adhesion", "telephone",
        ]
        read_only_fields = fields


class MembreDetailSerializer(serializers.ModelSerializer):
    """
    Sérialiseur complet pour le détail d'un membre.
    Inclut les mandats actifs et l'historique.
    """
    # Champs User
    username = serializers.CharField(source="user.username", read_only=True)
    nom_complet = serializers.CharField(source="user.get_full_name", read_only=True)
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    email = serializers.EmailField(source="user.email")

    # Champs relationnels
    pupitre_nom = serializers.CharField(source="pupitre.nom", read_only=True, default=None)
    mandats_actifs = MandatNestedSerializer(many=True, read_only=True, source="mandats")
    groupes = serializers.SerializerMethodField()

    class Meta:
        model = Membre
        fields = [
            "id", "username", "numero_membre",
            "nom_complet", "first_name", "last_name", "email",
            "pupitre", "pupitre_nom", "statut",
            "date_adhesion", "telephone", "photo", "notes",
            "mandats_actifs", "groupes",
            "is_deleted", "deleted_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "username", "numero_membre",
            "is_deleted", "deleted_at", "created_at", "updated_at",
        ]

    def get_groupes(self, obj) -> list[str]:
        """Groupes Django de l'utilisateur."""
        return list(obj.user.groups.values_list("name", flat=True))

    def update(self, instance, validated_data):
        """Met à jour les champs User et Membre ensemble."""
        user_data = validated_data.pop("user", {})

        # Mise à jour des champs User
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()

        # Mise à jour des champs Membre
        return super().update(instance, validated_data)
