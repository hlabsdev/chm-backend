"""
ChoirManager — Communications Views
=====================================
API des annonces de la chorale.

Lecture : tous les membres authentifiés (fil d'annonces de leur chorale).
Écriture : bureau ou maître de chœur uniquement.
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from core.mixins import ChoraleFilterMixin, SoftDeleteMixin
from core.permissions import IsBureauOrMaitreChoeur

from .models import Annonce
from .serializers import AnnonceSerializer


class AnnonceViewSet(SoftDeleteMixin, ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Annonces — fil d'informations de la chorale.

    GET    /api/communications/annonces/       → fil actif (non expirées)
    POST   /api/communications/annonces/       → publier (bureau / MDC)
    GET    /api/communications/annonces/{id}/  → détail
    PATCH  /api/communications/annonces/{id}/  → modifier (bureau / MDC)
    DELETE /api/communications/annonces/{id}/  → soft-delete (bureau / MDC)

    Par défaut, le fil masque les annonces expirées. `?inclure_expirees=true`
    les réintègre (utile au bureau pour consulter l'historique).
    """
    queryset = Annonce.objects.select_related("auteur__user")
    serializer_class = AnnonceSerializer
    search_fields = ["titre", "contenu"]
    ordering_fields = ["created_at", "epinglee", "date_expiration"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrMaitreChoeur()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("inclure_expirees") != "true":
            today = timezone.now().date()
            qs = qs.filter(Q(date_expiration__isnull=True) | Q(date_expiration__gte=today))
        return qs

    def perform_create(self, serializer):
        membre = getattr(self.request.user, "membre", None)
        if membre is None:
            raise PermissionDenied("Seul un membre rattaché à une chorale peut publier une annonce.")
        chorale = getattr(self.request, "chorale", None)
        if not chorale and not self.request.user.is_superuser:
            raise PermissionDenied("Vous devez être associé à une chorale pour publier une annonce.")
        annonce = serializer.save(chorale=chorale, auteur=membre)

        # Notifier tous les membres actifs (in-app uniquement — pas d'email
        # de masse), sauf l'auteur qui sait déjà ce qu'il vient de publier.
        from membres.models import Membre
        from notifications.models import Notification
        from notifications.services import notifier_groupe
        destinataires = Membre.objects.filter(
            chorale=annonce.chorale, is_deleted=False,
            statut__in=[Membre.Statut.ACTIF, Membre.Statut.STAGIAIRE],
        ).exclude(pk=membre.pk)
        notifier_groupe(
            destinataires,
            type_notification=Notification.Type.ANNONCE,
            titre=f"Nouvelle annonce : {annonce.titre}",
            message=annonce.contenu[:200],
            lien="/annonces",
        )
