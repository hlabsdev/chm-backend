"""
ChoirManager — Presences Views
=================================
API REST pour la gestion des répétitions, du pointage et des permissions.
"""

from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.mixins import ChoraleFilterMixin
from core.permissions import IsBureau, IsBureauOrMaitreChoeur, IsOwnerOrBureau

from .models import Presence, PermissionRequest, Repetition
from .serializers import (
    PermissionRequestSerializer,
    PresenceSerializer,
    RepetitionDetailSerializer,
    RepetitionListSerializer,
)


class RepetitionViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Répétitions — Séances de la chorale.

    Lecture : tous les membres authentifiés.
    Écriture : bureau ou maître de chœur.

    Action supplémentaire :
    POST /api/presences/repetitions/{id}/pointer/  → pointage groupé
    """
    queryset = Repetition.objects.select_related("dirigee_par__user")
    filterset_fields = ["date"]
    ordering_fields = ["date", "heure_debut"]

    def get_serializer_class(self):
        if self.action == "list":
            return RepetitionListSerializer
        return RepetitionDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]

    @action(detail=True, methods=["post"], permission_classes=[IsBureauOrMaitreChoeur])
    def pointer(self, request, pk=None):
        """
        Pointage groupé pour une répétition.
        Reçoit une liste de {membre_id, statut, motif?}.

        Body attendu :
        {
            "presences": [
                {"membre": 1, "statut": "present"},
                {"membre": 2, "statut": "absent", "motif": "Maladie"},
                {"membre": 3, "statut": "retard"}
            ]
        }
        """
        repetition = self.get_object()
        presences_data = request.data.get("presences", [])

        if not presences_data:
            return Response(
                {"detail": "La liste des présences est vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created, updated = 0, 0
        for item in presences_data:
            presence, was_created = Presence.objects.update_or_create(
                repetition=repetition,
                membre_id=item["membre"],
                chorale=repetition.chorale,
                defaults={
                    "statut": item["statut"],
                    "motif": item.get("motif", ""),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return Response(
            {
                "detail": f"Pointage enregistré. {created} créés, {updated} mis à jour.",
                "created": created,
                "updated": updated,
            },
            status=status.HTTP_200_OK,
        )


class PresenceViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Présences — Pointage individuel.
    Principalement utilisé en lecture pour les rapports.
    """
    queryset = Presence.objects.select_related(
        "membre__user", "membre__pupitre", "repetition"
    )
    serializer_class = PresenceSerializer
    filterset_fields = ["repetition", "membre", "statut"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]


class PermissionRequestViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Demandes de permission — Absences anticipées.

    Un membre peut créer sa propre demande.
    Le bureau/maître de chœur peut approuver ou refuser.

    Actions :
    POST /api/presences/permissions/{id}/approuver/
    POST /api/presences/permissions/{id}/refuser/
    """
    queryset = PermissionRequest.objects.select_related(
        "membre__user", "traitee_par__user"
    )
    serializer_class = PermissionRequestSerializer
    filterset_fields = ["statut", "membre"]

    def get_permissions(self):
        if self.action in ["create"]:
            return [permissions.IsAuthenticated()]
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]

    def perform_create(self, serializer):
        """Le membre connecté est automatiquement le demandeur."""
        chorale = getattr(self.request, "chorale", None)
        serializer.save(
            membre=self.request.user.membre,
            chorale=chorale,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsBureauOrMaitreChoeur])
    def approuver(self, request, pk=None):
        """Approuve une demande de permission."""
        demande = self.get_object()
        if demande.statut != PermissionRequest.StatutDemande.EN_ATTENTE:
            return Response(
                {"detail": "Cette demande a déjà été traitée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        demande.statut = PermissionRequest.StatutDemande.APPROUVEE
        demande.traitee_par = request.user.membre
        demande.date_traitement = timezone.now()
        demande.save()

        return Response({"detail": "Demande approuvée."})

    @action(detail=True, methods=["post"], permission_classes=[IsBureauOrMaitreChoeur])
    def refuser(self, request, pk=None):
        """Refuse une demande de permission."""
        demande = self.get_object()
        if demande.statut != PermissionRequest.StatutDemande.EN_ATTENTE:
            return Response(
                {"detail": "Cette demande a déjà été traitée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        demande.statut = PermissionRequest.StatutDemande.REFUSEE
        demande.traitee_par = request.user.membre
        demande.date_traitement = timezone.now()
        demande.save()

        return Response({"detail": "Demande refusée."})
