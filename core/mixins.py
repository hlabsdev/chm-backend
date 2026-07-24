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

        On injecte via `serializer.save(chorale=...)` — ce qui fonctionne même
        si le serializer n'expose pas de champ `chorale` (DRF fusionne les kwargs
        dans les validated_data). L'injection est conditionnée à la présence d'un
        champ `chorale` sur le MODÈLE, pas sur le serializer : certains modèles
        rattachés à une chorale ne le sont qu'indirectement (ex. PaiementCotisation,
        scopé via sa cotisation) et n'ont pas de FK `chorale` directe — leur passer
        `chorale=` lèverait un TypeError.
        """
        chorale = getattr(self.request, "chorale", None)

        if not chorale and not self.request.user.is_superuser:
            raise PermissionDenied(
                "Vous devez être associé à une chorale pour créer cet élément."
            )

        model = getattr(getattr(serializer, "Meta", None), "model", None)
        model_has_chorale = model is not None and any(
            f.name == "chorale" for f in model._meta.get_fields()
        )

        if chorale and model_has_chorale:
            serializer.save(chorale=chorale)
        else:
            # Soit le modèle n'a pas de FK chorale (rattachement indirect),
            # soit superuser sans chorale de contexte (chorale dans la payload).
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

        # L'action `restore` cible par définition un élément soft-deleted :
        # sans cette exception, le filtre ci-dessous rendait la restauration
        # inatteignable (404) pour un non-superuser — l'isolation par chorale
        # (ChoraleFilterMixin) reste appliquée en amont.
        if getattr(self, "action", None) == "restore":
            return qs

        # Permettre de voir les supprimés via ?include_deleted=true
        if self.request.query_params.get("include_deleted") == "true":
            if self.request.user.is_superuser:
                return qs
        return qs.filter(is_deleted=False)

    def perform_destroy(self, instance):
        """Soft-delete au lieu de supprimer physiquement."""
        instance.soft_delete()
