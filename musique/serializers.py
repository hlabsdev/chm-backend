"""
ChoirManager — Musique Serializers
====================================
"""

from rest_framework import serializers

from .models import Chant, Partition, SeanceChant


class PartitionSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les fichiers de partition."""
    type_voix_nom = serializers.CharField(
        source="type_voix.nom", read_only=True, default=None
    )

    class Meta:
        model = Partition
        fields = [
            "id", "chant", "titre", "fichier",
            "type_voix", "type_voix_nom",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ChantListSerializer(serializers.ModelSerializer):
    """Sérialiseur léger pour les listes du répertoire."""
    nombre_partitions = serializers.IntegerField(read_only=True)

    class Meta:
        model = Chant
        fields = [
            "id", "titre", "compositeur", "style",
            "tonalite", "nombre_partitions",
        ]
        read_only_fields = fields


class ChantDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur complet avec les partitions imbriquées."""
    partitions = PartitionSerializer(many=True, read_only=True)
    dernier_statut = serializers.SerializerMethodField()

    class Meta:
        model = Chant
        fields = [
            "id", "titre", "compositeur", "style",
            "tonalite", "tempo", "notes",
            "partitions", "dernier_statut",
            "is_deleted", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_deleted", "created_at", "updated_at"]

    def get_dernier_statut(self, obj) -> str | None:
        """Retourne le dernier statut d'apprentissage du chant."""
        derniere_seance = (
            obj.seances
            .order_by("-repetition__date")
            .values_list("statut", flat=True)
            .first()
        )
        return derniere_seance


class SeanceChantSerializer(serializers.ModelSerializer):
    """Sérialiseur pour le suivi d'apprentissage par séance."""
    chant_titre = serializers.CharField(source="chant.titre", read_only=True)
    repetition_date = serializers.DateField(source="repetition.date", read_only=True)

    class Meta:
        model = SeanceChant
        fields = [
            "id", "repetition", "repetition_date",
            "chant", "chant_titre",
            "statut", "notes", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
