"""
ChoirManager — Musique Views
===============================
API REST pour le répertoire musical.
"""

from rest_framework import viewsets, permissions

from core.mixins import ChoraleFilterMixin, SoftDeleteMixin
from core.permissions import IsBureauOrMaitreChoeur

from .models import Chant, Partition, SeanceChant
from .serializers import (
    ChantDetailSerializer,
    ChantListSerializer,
    PartitionSerializer,
    SeanceChantSerializer,
)


class ChantViewSet(SoftDeleteMixin, ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Répertoire — Chants de la chorale.

    Lecture : tous les membres authentifiés.
    Écriture : bureau ou maître de chœur.
    """
    queryset = Chant.objects.all()
    search_fields = ["titre", "compositeur"]
    ordering_fields = ["titre", "style", "created_at"]
    filterset_fields = ["style"]

    def get_serializer_class(self):
        if self.action == "list":
            return ChantListSerializer
        return ChantDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]


class PartitionViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Partitions — Fichiers de partitions liés aux chants.

    Lecture : tous les membres authentifiés.
    Écriture : bureau ou maître de chœur.
    """
    queryset = Partition.objects.select_related("chant", "type_voix")
    serializer_class = PartitionSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]


class SeanceChantViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Suivi d'apprentissage — Progression des chants par séance.

    Lecture : tous les membres authentifiés.
    Écriture : maître de chœur ou bureau.
    """
    queryset = SeanceChant.objects.select_related("chant", "repetition")
    serializer_class = SeanceChantSerializer
    filterset_fields = ["chant", "repetition", "statut"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]
