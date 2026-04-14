"""
ChoirManager — Finances Serializers
======================================
"""

from django.db import transaction
from rest_framework import serializers

from .models import (
    CampagneCotisation,
    CategorieMouvement,
    Cotisation,
    Mouvement,
    PaiementCotisation,
)


class CategorieMouvementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieMouvement
        fields = ["id", "nom", "type_mouvement", "description"]
        read_only_fields = ["id"]


class MouvementSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les mouvements financiers (journal de caisse)."""
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True)
    membre_nom = serializers.CharField(
        source="membre.nom_complet", read_only=True, default=None
    )
    enregistre_par_nom = serializers.CharField(
        source="enregistre_par.nom_complet", read_only=True
    )

    class Meta:
        model = Mouvement
        fields = [
            "id", "date", "montant", "sens",
            "categorie", "categorie_nom",
            "motif",
            "membre", "membre_nom",
            "enregistre_par", "enregistre_par_nom",
            "piece_jointe",
            "is_deleted", "created_at",
        ]
        read_only_fields = ["id", "enregistre_par", "is_deleted", "created_at"]


class CampagneCotisationListSerializer(serializers.ModelSerializer):
    """Sérialiseur léger pour la liste des campagnes."""
    montant_total_attendu = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    montant_total_collecte = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    taux_recouvrement = serializers.FloatField(read_only=True)
    nombre_cotisations = serializers.SerializerMethodField()

    class Meta:
        model = CampagneCotisation
        fields = [
            "id", "nom", "type_campagne", "montant_unitaire",
            "date_debut", "date_fin", "is_obligatoire", "is_active",
            "montant_total_attendu", "montant_total_collecte",
            "taux_recouvrement", "nombre_cotisations",
        ]
        read_only_fields = ["id"]

    def get_nombre_cotisations(self, obj) -> int:
        return obj.cotisations.count()


class CotisationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les cotisations individuelles."""
    membre_nom = serializers.CharField(source="membre.nom_complet", read_only=True)
    campagne_nom = serializers.CharField(source="campagne.nom", read_only=True)
    reste_a_payer = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    is_solde = serializers.BooleanField(read_only=True)

    class Meta:
        model = Cotisation
        fields = [
            "id", "campagne", "campagne_nom",
            "membre", "membre_nom",
            "montant_du", "montant_paye", "statut",
            "reste_a_payer", "is_solde",
            "notes", "created_at",
        ]
        read_only_fields = ["id", "montant_paye", "statut", "created_at"]


class PaiementCotisationSerializer(serializers.ModelSerializer):
    """
    Sérialiseur pour les paiements de cotisation.
    Crée automatiquement un Mouvement dans le journal de caisse.
    """

    class Meta:
        model = PaiementCotisation
        fields = [
            "id", "cotisation", "montant", "date_paiement",
            "mouvement", "notes", "created_at",
        ]
        read_only_fields = ["id", "mouvement", "created_at"]

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être positif.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        """
        Crée le paiement ET le mouvement correspondant dans le journal.
        Met à jour le montant_paye et le statut de la cotisation.
        """
        cotisation = validated_data["cotisation"]
        montant = validated_data["montant"]
        date_paiement = validated_data["date_paiement"]
        request = self.context.get("request")

        # 1. Créer le mouvement dans le journal de caisse
        # Trouver ou créer la catégorie "Cotisation"
        categorie, _ = CategorieMouvement.objects.get_or_create(
            chorale=cotisation.chorale,
            nom="Cotisation",
            defaults={"type_mouvement": "entree"},
        )

        mouvement = Mouvement.objects.create(
            chorale=cotisation.chorale,
            date=date_paiement,
            montant=montant,
            sens=Mouvement.Sens.ENTREE,
            categorie=categorie,
            motif=f"Cotisation : {cotisation.campagne.nom} — {cotisation.membre.nom_complet}",
            membre=cotisation.membre,
            enregistre_par=request.user.membre if request else cotisation.membre,
        )

        # 2. Créer le paiement
        validated_data["mouvement"] = mouvement
        paiement = super().create(validated_data)

        # 3. Mettre à jour la cotisation
        cotisation.montant_paye += montant
        cotisation.recalculer_statut()
        cotisation.save(update_fields=["montant_paye", "statut", "updated_at"])

        return paiement


class EtatCaisseSerializer(serializers.Serializer):
    """Sérialiseur pour l'état de caisse (lecture seule, calculé)."""
    total_entrees = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_sorties = serializers.DecimalField(max_digits=12, decimal_places=2)
    solde = serializers.DecimalField(max_digits=12, decimal_places=2)
    nombre_mouvements = serializers.IntegerField()
    periode_debut = serializers.DateField()
    periode_fin = serializers.DateField()
