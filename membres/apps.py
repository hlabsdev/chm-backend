"""
ChoirManager — Membres Application Config
"""

from django.apps import AppConfig


class MembresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "membres"
    verbose_name = "Membres & Structure"

    def ready(self):
        """Connecte les signaux au démarrage de l'application."""
        import membres.signals  # noqa: F401
