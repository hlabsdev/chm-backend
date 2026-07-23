"""
ChoirManager — Communications Serializers
===========================================
"""

from rest_framework import serializers

from .models import Annonce


class AnnonceSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.CharField(source="auteur.nom_complet", read_only=True)
    est_expiree = serializers.SerializerMethodField()

    class Meta:
        model = Annonce
        fields = [
            "id", "titre", "contenu",
            "auteur", "auteur_nom",
            "piece_jointe", "epinglee", "date_expiration",
            "est_expiree", "created_at", "updated_at",
        ]
        # auteur est injecté côté serveur (membre connecté), jamais choisi par le client.
        read_only_fields = ["id", "auteur", "created_at", "updated_at"]

    def get_est_expiree(self, obj) -> bool:
        from django.utils import timezone
        return bool(obj.date_expiration and obj.date_expiration < timezone.now().date())
