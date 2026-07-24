"""
ChoirManager — Notifications Views
=====================================
Chaque membre ne voit et ne gère QUE ses propres notifications — le
filtrage est par destinataire (pas seulement par chorale), un superuser
n'a pas non plus vocation à lire les notifications des autres.
"""

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    GET  /api/notifications/                → mes notifications (récentes d'abord)
    GET  /api/notifications/non-lues/       → compteur (badge de la nav)
    POST /api/notifications/{id}/lue/       → marquer comme lue
    POST /api/notifications/tout-lu/        → tout marquer comme lu
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        membre = getattr(self.request.user, "membre", None)
        if membre is None:
            return Notification.objects.none()
        return Notification.objects.filter(destinataire=membre)

    @action(detail=False, methods=["get"], url_path="non-lues")
    def non_lues(self, request):
        return Response({"count": self.get_queryset().filter(lue=False).count()})

    @action(detail=True, methods=["post"])
    def lue(self, request, pk=None):
        notif = self.get_object()
        if not notif.lue:
            notif.lue = True
            notif.save(update_fields=["lue", "updated_at"])
        return Response(NotificationSerializer(notif).data)

    @action(detail=False, methods=["post"], url_path="tout-lu")
    def tout_lu(self, request):
        nb = self.get_queryset().filter(lue=False).update(lue=True)
        return Response({"detail": f"{nb} notification(s) marquée(s) comme lue(s).", "count": nb})
