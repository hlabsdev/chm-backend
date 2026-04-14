"""
ChoirManager — Musique Application Config
"""

from django.apps import AppConfig


class MusiqueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "musique"
    verbose_name = "Répertoire Musical"
