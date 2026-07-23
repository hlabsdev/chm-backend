"""
ChoirManager — Core Admin
===========================
Enregistrement de Chorale dans le Django admin : c'est aujourd'hui le
seul écran permettant à un superuser de consulter/ajuster une chorale
sans passer par le shell. La création proprement dite (avec ses postes,
pupitres et son premier compte Bureau) passe par la commande
`provision_chorale` — l'admin seul ne suffit pas à obtenir une chorale
utilisable.
"""

from django.contrib import admin

from .models import Chorale


@admin.register(Chorale)
class ChoraleAdmin(admin.ModelAdmin):
    list_display = ["nom", "prefix", "currency", "is_active", "date_creation", "created_at"]
    list_filter = ["is_active", "currency"]
    search_fields = ["nom", "prefix", "email"]
    readonly_fields = ["created_at", "updated_at"]
