"""
ChoirManager — Throttles anti-abus
=====================================
Limites de fréquence par IP pour les endpoints publics (non authentifiés).
Chaque scope a un taux dédié dans REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
(chm_config/settings.py) — les valeurs concrètes vivent là, pas ici.
"""

from rest_framework.throttling import AnonRateThrottle


class DemandeChoraleThrottle(AnonRateThrottle):
    """Limite les soumissions du formulaire public de demande d'adhésion chorale."""
    scope = "demande_chorale"


class InvitationVerifierThrottle(AnonRateThrottle):
    """Limite les tentatives de vérification d'un code d'invitation (anti brute-force)."""
    scope = "invitation_verifier"


class InvitationRejoindreThrottle(AnonRateThrottle):
    """Limite les tentatives d'inscription via code d'invitation."""
    scope = "invitation_rejoindre"
