"""
ChoirManager — Permissions DRF
================================
Permissions basées sur les Groupes Django, synchronisés
automatiquement via le signal post_save sur Mandat.
"""

from rest_framework.permissions import BasePermission


class IsInGroup(BasePermission):
    """
    Permission générique : vérifie que l'utilisateur appartient
    à au moins un des groupes spécifiés dans `required_groups`.

    Les super admins passent toujours.

    Usage :
        class MyView(APIView):
            permission_classes = [IsBureau]
    """
    required_groups = []

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Super admin → accès total
        if request.user.is_superuser:
            return True

        # Vérifier l'intersection entre les groupes du user et les groupes requis
        user_groups = set(
            request.user.groups.values_list("name", flat=True)
        )
        return bool(user_groups & set(self.required_groups))


class IsBureau(IsInGroup):
    """Accès réservé aux membres du bureau (élus)."""
    required_groups = ["bureau"]


class IsTresorier(IsInGroup):
    """Accès réservé au trésorier."""
    required_groups = ["tresorier"]


class IsMaitreChoeur(IsInGroup):
    """Accès réservé aux maîtres de chœur."""
    required_groups = ["maitre_choeur"]


class IsChefPupitre(IsInGroup):
    """Accès réservé aux chefs de pupitre."""
    required_groups = ["chef_pupitre"]


class IsMembreActif(IsInGroup):
    """Accès réservé aux membres actifs."""
    required_groups = ["membre_actif"]


class IsBureauOrMaitreChoeur(IsInGroup):
    """Accès bureau OU maître de chœur."""
    required_groups = ["bureau", "maitre_choeur"]


class IsBureauOrTresorier(IsInGroup):
    """Accès bureau OU trésorier (pour les finances)."""
    required_groups = ["bureau", "tresorier"]


class IsOwnerOrBureau(BasePermission):
    """
    Permission objet : autorise si l'utilisateur est le propriétaire
    de la ressource OU membre du bureau.

    Le ViewSet doit définir `owner_field` (défaut: 'membre').
    """
    owner_field = "membre"

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True

        # Vérifier si l'utilisateur est le propriétaire
        owner = getattr(obj, self.owner_field, None)
        if owner and hasattr(request.user, "membre"):
            if owner == request.user.membre:
                return True

        # Sinon, vérifier s'il est membre du bureau
        user_groups = set(
            request.user.groups.values_list("name", flat=True)
        )
        return "bureau" in user_groups
