"""
ChoirManager — Membres Views (ViewSets DRF)
=============================================
API REST pour la gestion des pupitres, postes, membres et mandats.
Tous les ViewSets utilisent ChoraleFilterMixin pour l'isolation par chorale.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from core.mixins import ChoraleFilterMixin, SoftDeleteMixin
from core.permissions import IsBureau, IsBureauOrMaitreChoeur, IsMembreActif

from .filters import MembreFilter
from .models import Mandat, Membre, Poste, Pupitre
from .serializers import (
    MandatSerializer,
    MembreDetailSerializer,
    MembreListSerializer,
    PosteSerializer,
    PupitreSerializer,
)


class PupitreViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Pupitres — Sections vocales de la chorale.

    GET    /api/membres/pupitres/          → liste
    POST   /api/membres/pupitres/          → créer (bureau)
    GET    /api/membres/pupitres/{id}/     → détail
    PUT    /api/membres/pupitres/{id}/     → modifier (bureau)
    DELETE /api/membres/pupitres/{id}/     → supprimer (bureau)
    """
    queryset = Pupitre.objects.all()
    serializer_class = PupitreSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureau()]


class PosteViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Postes — Rôles organisationnels de la chorale.

    Accès : Bureau uniquement (sauf lecture).

    GET    /api/membres/postes/          → liste
    POST   /api/membres/postes/          → créer
    GET    /api/membres/postes/{id}/     → détail
    PUT    /api/membres/postes/{id}/     → modifier
    DELETE /api/membres/postes/{id}/     → supprimer
    """
    queryset = Poste.objects.prefetch_related("groupes")
    serializer_class = PosteSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureau()]


class MembreViewSet(SoftDeleteMixin, ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Membres — Gestion des membres de la chorale.

    GET    /api/membres/                  → liste (tous les membres actifs)
    POST   /api/membres/                  → créer (bureau)
    GET    /api/membres/{id}/             → détail
    PUT    /api/membres/{id}/             → modifier (bureau)
    DELETE /api/membres/{id}/             → soft-delete (bureau)

    Actions supplémentaires :
    POST   /api/membres/{id}/restore/     → restaurer un membre soft-deleted
    """
    queryset = Membre.objects.select_related("user", "pupitre", "chorale")
    filterset_class = MembreFilter
    search_fields = [
        "user__first_name", "user__last_name",
        "user__email", "numero_membre",
    ]
    ordering_fields = ["user__last_name", "date_adhesion", "statut"]

    def get_serializer_class(self):
        if self.action == "list":
            return MembreListSerializer
        return MembreDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureau()]

    @action(detail=True, methods=["post"], permission_classes=[IsBureau])
    def restore(self, request, pk=None):
        """Restaure un membre soft-deleted."""
        membre = self.get_object()
        if not membre.is_deleted:
            return Response(
                {"detail": "Ce membre n'est pas supprimé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membre.restore()
        membre.statut = Membre.Statut.ACTIF
        membre.save(update_fields=["statut"])

        # Réactiver le User Django
        membre.user.is_active = True
        membre.user.save(update_fields=["is_active"])

        return Response(
            {"detail": f"{membre.nom_complet} a été restauré."},
            status=status.HTTP_200_OK,
        )


class MandatViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Mandats — Attribution de postes aux membres.

    GET    /api/membres/mandats/           → liste
    POST   /api/membres/mandats/           → créer (bureau)
    GET    /api/membres/mandats/{id}/      → détail
    PUT    /api/membres/mandats/{id}/      → modifier (bureau)

    Actions supplémentaires :
    POST   /api/membres/mandats/{id}/terminer/  → clôturer un mandat
    """
    queryset = Mandat.objects.select_related("membre__user", "poste")
    serializer_class = MandatSerializer
    permission_classes = [IsBureau]
    filterset_fields = ["membre", "poste", "is_active"]

    def get_queryset(self):
        """
        Filtre par chorale via le membre (le mandat n'a pas de FK chorale directe).
        """
        qs = Mandat.objects.select_related("membre__user", "poste")

        if self.request.user.is_superuser:
            return qs

        chorale = getattr(self.request, "chorale", None)
        if chorale is not None:
            return qs.filter(membre__chorale=chorale)

        return qs.none()

    @action(detail=True, methods=["post"])
    def terminer(self, request, pk=None):
        """
        Clôture un mandat actif.
        Le signal post_save mettra à jour les groupes Django automatiquement.
        """
        mandat = self.get_object()
        if not mandat.is_active:
            return Response(
                {"detail": "Ce mandat est déjà terminé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_fin = request.data.get("date_fin")
        mandat.terminer(date_fin=date_fin)

        return Response(
            {"detail": f"Mandat de {mandat.membre.nom_complet} terminé."},
            status=status.HTTP_200_OK,
        )
