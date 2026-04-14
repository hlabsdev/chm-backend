"""
ChoirManager — Presences Serializers
=======================================
"""

from rest_framework import serializers

from .models import Presence, PermissionRequest, Repetition


class PresenceSerializer(serializers.ModelSerializer):
    """Sérialiseur pour le pointage."""
    membre_nom = serializers.CharField(source="membre.nom_complet", read_only=True)
    membre_pupitre = serializers.CharField(
        source="membre.pupitre.nom", read_only=True, default=None
    )

    class Meta:
        model = Presence
        fields = [
            "id", "repetition", "membre", "membre_nom",
            "membre_pupitre", "statut", "motif", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class RepetitionListSerializer(serializers.ModelSerializer):
    """Sérialiseur léger pour la liste des répétitions."""
    dirigee_par_nom = serializers.CharField(
        source="dirigee_par.nom_complet", read_only=True, default=None
    )
    nombre_presents = serializers.IntegerField(read_only=True)
    taux_presence = serializers.FloatField(read_only=True)

    class Meta:
        model = Repetition
        fields = [
            "id", "date", "heure_debut", "heure_fin",
            "lieu", "dirigee_par", "dirigee_par_nom",
            "nombre_presents", "taux_presence",
        ]
        read_only_fields = fields


class RepetitionDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur complet avec les présences et chants travaillés."""
    dirigee_par_nom = serializers.CharField(
        source="dirigee_par.nom_complet", read_only=True, default=None
    )
    presences = PresenceSerializer(many=True, read_only=True)
    nombre_presents = serializers.IntegerField(read_only=True)
    nombre_absents = serializers.IntegerField(read_only=True)
    taux_presence = serializers.FloatField(read_only=True)

    class Meta:
        model = Repetition
        fields = [
            "id", "date", "heure_debut", "heure_fin",
            "lieu", "resume",
            "dirigee_par", "dirigee_par_nom",
            "presences", "nombre_presents", "nombre_absents",
            "taux_presence",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PermissionRequestSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les demandes de permission."""
    membre_nom = serializers.CharField(source="membre.nom_complet", read_only=True)
    traitee_par_nom = serializers.CharField(
        source="traitee_par.nom_complet", read_only=True, default=None
    )

    class Meta:
        model = PermissionRequest
        fields = [
            "id", "membre", "membre_nom",
            "repetition", "date_debut", "date_fin",
            "motif", "statut",
            "traitee_par", "traitee_par_nom", "date_traitement",
            "created_at",
        ]
        read_only_fields = ["id", "traitee_par", "date_traitement", "created_at"]

    def validate(self, data):
        if data.get("date_fin") and data.get("date_debut"):
            if data["date_fin"] < data["date_debut"]:
                raise serializers.ValidationError({
                    "date_fin": "La date de fin ne peut pas être antérieure à la date de début."
                })
        return data
