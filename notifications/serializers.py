"""
ChoirManager — Notifications Serializers
===========================================
"""

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "type_notification", "titre", "message", "lien",
            "lue", "created_at",
        ]
        read_only_fields = fields
