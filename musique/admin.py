"""
ChoirManager — Musique Admin
===============================
"""

from django.contrib import admin

from .models import Chant, Partition, SeanceChant


@admin.register(Chant)
class ChantAdmin(admin.ModelAdmin):
    list_display = ["titre", "compositeur", "style", "chorale", "is_deleted"]
    list_filter = ["chorale", "style", "is_deleted"]
    search_fields = ["titre", "compositeur"]


@admin.register(Partition)
class PartitionAdmin(admin.ModelAdmin):
    list_display = ["titre", "chant", "type_voix", "chorale"]
    list_filter = ["chorale", "type_voix"]
    raw_id_fields = ["chant"]


@admin.register(SeanceChant)
class SeanceChantAdmin(admin.ModelAdmin):
    list_display = ["chant", "repetition", "statut", "chorale"]
    list_filter = ["chorale", "statut"]
    raw_id_fields = ["chant", "repetition"]
