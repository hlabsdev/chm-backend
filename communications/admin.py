"""
ChoirManager — Communications Admin
"""

from django.contrib import admin

from .models import Annonce


@admin.register(Annonce)
class AnnonceAdmin(admin.ModelAdmin):
    list_display = ["titre", "chorale", "auteur", "epinglee", "date_expiration", "is_deleted", "created_at"]
    list_filter = ["chorale", "epinglee", "is_deleted"]
    search_fields = ["titre", "contenu"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]
