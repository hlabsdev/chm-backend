"""
ChoirManager — Mixins ViewSet
==============================
Mixins réutilisables pour les ViewSets DRF.
"""

from rest_framework.exceptions import PermissionDenied


class ChoraleFilterMixin:
    """
    Mixin ViewSet : filtre automatiquement le queryset
    par la chorale du user connecté.

    Comportement :
    - Super admin   → voit toutes les données (pas de filtre)
    - Membre        → voit uniquement les données de sa chorale
    - Non-membre    → queryset vide

    Usage :
        class MyViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
            queryset = MyModel.objects.all()
    """

    def get_queryset(self):
        qs = super().get_queryset()

        if self.request.user.is_superuser:
            return qs

        chorale = getattr(self.request, "chorale", None)
        if chorale is not None:
            return qs.filter(chorale=chorale)

        # L'utilisateur n'a pas de chorale associée
        return qs.none()

    def perform_create(self, serializer):
        """
        Injecte automatiquement la chorale du user connecté
        lors de la création d'un objet.
        """
        chorale = getattr(self.request, "chorale", None)

        if chorale is None and not self.request.user.is_superuser:
            raise PermissionDenied(
                "Vous devez être associé à une chorale pour créer cet élément."
            )

        # Si le serializer accepte 'chorale', l'injecter
        if "chorale" in serializer.fields:
            serializer.save(chorale=chorale)
        else:
            serializer.save()


class SoftDeleteMixin:
    """
    Mixin ViewSet : remplace la suppression physique par un soft-delete.
    Filtre également les éléments soft-deleted du queryset par défaut.

    Usage :
        class MyViewSet(SoftDeleteMixin, ChoraleFilterMixin, viewsets.ModelViewSet):
            queryset = MyModel.objects.all()
    """

    def get_queryset(self):
        """Exclut les éléments soft-deleted par défaut."""
        qs = super().get_queryset()

        # Permettre de voir les supprimés via ?include_deleted=true
        if self.request.query_params.get("include_deleted") == "true":
            if self.request.user.is_superuser:
                return qs
        return qs.filter(is_deleted=False)

    def perform_destroy(self, instance):
        """Soft-delete au lieu de supprimer physiquement."""
        instance.soft_delete()
