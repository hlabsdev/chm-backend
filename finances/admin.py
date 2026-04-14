"""
ChoirManager — Finances Admin
=================================
"""

from django.contrib import admin

from .models import (
    CampagneCotisation,
    CategorieMouvement,
    Cotisation,
    Mouvement,
    PaiementCotisation,
)


@admin.register(CategorieMouvement)
class CategorieMouvementAdmin(admin.ModelAdmin):
    list_display = ["nom", "type_mouvement", "chorale"]
    list_filter = ["chorale", "type_mouvement"]


@admin.register(Mouvement)
class MouvementAdmin(admin.ModelAdmin):
    list_display = ["date", "montant", "sens", "categorie", "motif", "membre", "chorale"]
    list_filter = ["chorale", "sens", "categorie", "is_deleted"]
    search_fields = ["motif"]
    date_hierarchy = "date"
    raw_id_fields = ["membre", "enregistre_par"]


@admin.register(CampagneCotisation)
class CampagneCotisationAdmin(admin.ModelAdmin):
    list_display = [
        "nom", "type_campagne", "montant_unitaire",
        "date_debut", "date_fin", "is_obligatoire", "is_active", "chorale",
    ]
    list_filter = ["chorale", "type_campagne", "is_active"]
    search_fields = ["nom"]


@admin.register(Cotisation)
class CotisationAdmin(admin.ModelAdmin):
    list_display = [
        "membre", "campagne", "montant_du", "montant_paye",
        "statut", "chorale",
    ]
    list_filter = ["chorale", "statut", "campagne"]
    raw_id_fields = ["membre", "campagne"]


@admin.register(PaiementCotisation)
class PaiementCotisationAdmin(admin.ModelAdmin):
    list_display = ["cotisation", "montant", "date_paiement"]
    date_hierarchy = "date_paiement"
    raw_id_fields = ["cotisation", "mouvement"]
