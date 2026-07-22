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

        # `request.chorale` est un SimpleLazyObject (cf. ChoraleMiddleware) :
        # on teste la véracité, ce qui force l'évaluation et évite le piège
        # du `is not None` (l'objet paresseux n'est jamais identique à None).
        chorale = getattr(self.request, "chorale", None)
        if chorale:
            return qs.filter(chorale=chorale)

        # L'utilisateur n'a pas de chorale associée
        return qs.none()

    def perform_create(self, serializer):
        """
        Injecte automatiquement la chorale du user connecté lors de la création.

        `serializer.save(chorale=...)` fonctionne même si le serializer n'expose
        PAS de champ `chorale` : DRF fusionne les kwargs de save() dans les
        validated_data passées à Model.objects.create(). C'est volontaire — les
        serializers n'exposent pas `chorale` (déduite du tenant, jamais fournie
        par le client). Ne PAS conditionner l'injection à la présence du champ :
        sinon la FK chorale (NOT NULL) reste vide et la création échoue.
        """
        chorale = getattr(self.request, "chorale", None)

        if not chorale and not self.request.user.is_superuser:
            raise PermissionDenied(
                "Vous devez être associé à une chorale pour créer cet élément."
            )

        if chorale:
            serializer.save(chorale=chorale)
        else:
            # Superuser sans chorale de contexte : la chorale doit être fournie
            # dans la payload (cas d'administration multi-chorale).
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
