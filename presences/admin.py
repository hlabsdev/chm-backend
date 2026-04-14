"""
ChoirManager — Presences Admin
=================================
"""

from django.contrib import admin

from .models import Presence, PermissionRequest, Repetition


@admin.register(Repetition)
class RepetitionAdmin(admin.ModelAdmin):
    list_display = ["date", "heure_debut", "lieu", "dirigee_par", "chorale"]
    list_filter = ["chorale", "date"]
    search_fields = ["lieu", "resume"]
    date_hierarchy = "date"


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ["membre", "repetition", "statut"]
    list_filter = ["chorale", "statut", "repetition__date"]
    raw_id_fields = ["membre", "repetition"]


@admin.register(PermissionRequest)
class PermissionRequestAdmin(admin.ModelAdmin):
    list_display = ["membre", "date_debut", "date_fin", "statut", "traitee_par"]
    list_filter = ["chorale", "statut"]
    raw_id_fields = ["membre", "traitee_par"]
