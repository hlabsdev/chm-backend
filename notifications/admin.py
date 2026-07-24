"""
ChoirManager — Notifications Admin (vue superuser, lecture/purge)
"""

from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["titre", "destinataire", "type_notification", "lue", "created_at"]
    list_filter = ["type_notification", "lue", "chorale"]
    search_fields = ["titre", "message", "destinataire__user__last_name"]
    readonly_fields = ["created_at", "updated_at"]
