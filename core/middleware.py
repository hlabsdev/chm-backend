"""
ChoirManager — Middleware Chorale
==================================
Injecte le contexte de la chorale active dans chaque requête.
"""

from django.utils.functional import SimpleLazyObject


class ChoraleMiddleware:
    """
    Middleware qui injecte `request.chorale` à partir du Membre connecté.

    Comportement (valeur résolue) :
    - Utilisateur non authentifié   → None
    - Super admin                   → None (accès global)
    - Membre authentifié            → membre.chorale

    IMPORTANT — résolution paresseuse :
    Avec l'authentification JWT, DRF ne renseigne `request.user` qu'au niveau
    de la vue (dans `initial()`), donc APRÈS le passage du middleware. Résoudre
    la chorale immédiatement ici lirait un utilisateur encore anonyme et
    donnerait toujours None. On assigne donc un `SimpleLazyObject` : la chorale
    n'est calculée qu'au premier accès (dans le ViewSet), quand `request.user`
    est bien l'utilisateur JWT authentifié.

    Utilisé par ChoraleFilterMixin dans les ViewSets pour isoler
    automatiquement les données par chorale.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.chorale = SimpleLazyObject(lambda: self._resolve_chorale(request))
        return self.get_response(request)

    @staticmethod
    def _resolve_chorale(request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not user.is_superuser:
            membre = getattr(user, "membre", None)
            # Chorale suspendue (is_active=False) → None : les tokens déjà
            # émis restent techniquement valides, mais ChoraleFilterMixin
            # renverra alors des querysets vides — la suspension prend effet
            # immédiatement, sans attendre l'expiration des JWT.
            if membre is not None and membre.chorale.is_active:
                return membre.chorale
        return None
