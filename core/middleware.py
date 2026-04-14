"""
ChoirManager — Middleware Chorale
==================================
Injecte le contexte de la chorale active dans chaque requête.
"""


class ChoraleMiddleware:
    """
    Middleware qui injecte `request.chorale` à partir du Membre connecté.

    Comportement :
    - Utilisateur non authentifié   → request.chorale = None
    - Super admin                   → request.chorale = None (accès global)
    - Membre authentifié            → request.chorale = membre.chorale

    Utilisé par ChoraleFilterMixin dans les ViewSets pour isoler
    automatiquement les données par chorale.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.chorale = None

        if hasattr(request, "user") and request.user.is_authenticated:
            # Super admin → pas de filtrage chorale, accès global
            if not request.user.is_superuser:
                membre = getattr(request.user, "membre", None)
                if membre is not None:
                    request.chorale = membre.chorale

        response = self.get_response(request)
        return response
