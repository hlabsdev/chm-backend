"""
ChoirManager — Membres Admin
==============================
Configuration de l'administration Django pour le module Membres.
"""

from django.contrib import admin

from .models import InvitationChorale, Mandat, Membre, Poste, Pupitre


@admin.register(Pupitre)
class PupitreAdmin(admin.ModelAdmin):
    list_display = ["nom", "categorie", "chorale", "ordre"]
    list_filter = ["chorale", "categorie"]
    search_fields = ["nom"]
    ordering = ["chorale", "ordre", "nom"]


@admin.register(Poste)
class PosteAdmin(admin.ModelAdmin):
    list_display = ["nom", "type_poste", "chorale", "unique_actif"]
    list_filter = ["chorale", "type_poste"]
    search_fields = ["nom"]
    filter_horizontal = ["groupes"]


@admin.register(Membre)
class MembreAdmin(admin.ModelAdmin):
    list_display = [
        "numero_membre", "nom_complet", "pupitre",
        "statut", "chorale", "is_deleted",
    ]
    list_filter = ["chorale", "statut", "pupitre", "is_deleted"]
    search_fields = [
        "user__first_name", "user__last_name",
        "user__email", "numero_membre",
    ]
    raw_id_fields = ["user"]
    readonly_fields = ["numero_membre", "created_at", "updated_at", "deleted_at"]

    def nom_complet(self, obj):
        return obj.nom_complet
    nom_complet.short_description = "Nom complet"


@admin.register(Mandat)
class MandatAdmin(admin.ModelAdmin):
    list_display = ["membre", "poste", "date_debut", "date_fin", "is_active"]
    list_filter = ["is_active", "poste__chorale", "poste__type_poste"]
    search_fields = [
        "membre__user__first_name", "membre__user__last_name",
        "poste__nom",
    ]
    raw_id_fields = ["membre", "poste"]


@admin.register(InvitationChorale)
class InvitationChoraleAdmin(admin.ModelAdmin):
    """Vue superuser en lecture — la gestion courante se fait par le Bureau via l'app."""
    list_display = ["code", "chorale", "cree_par", "is_active", "expire_le", "nombre_utilisations", "max_utilisations", "created_at"]
    list_filter = ["chorale", "is_active"]
    search_fields = ["code", "note"]
    raw_id_fields = ["cree_par", "pupitre_suggere"]
    readonly_fields = ["code", "nombre_utilisations", "created_at", "updated_at"]
