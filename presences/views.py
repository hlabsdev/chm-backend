"""
ChoirManager — Presences Views
=================================
API REST pour la gestion des répétitions, du pointage et des permissions.
"""

from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
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

    def perform_create(self, serializer):
        """
        Injecte la chorale (via le mixin) et, par défaut, désigne le
        créateur (généralement le maître de chœur) comme dirigeant de la
        séance — sauf s'il a explicitement fourni un autre `dirigee_par`.
        """
        chorale = getattr(self.request, "chorale", None)
        extra = {"chorale": chorale} if chorale else {}
        if not serializer.validated_data.get("dirigee_par"):
            membre = getattr(self.request.user, "membre", None)
            if membre is not None:
                extra["dirigee_par"] = membre
        serializer.save(**extra)

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

    POST = upsert idempotent sur (repetition, membre) : l'écran de pointage
    mobile envoie chaque tap immédiatement ; un retry réseau ne doit jamais
    provoquer une erreur d'unicité ni un doublon. Re-poster le même couple
    met simplement à jour le statut (200), la création initiale renvoie 201.
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

    def create(self, request, *args, **kwargs):
        """Upsert : créer ou mettre à jour le pointage d'un membre."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        repetition = serializer.validated_data["repetition"]
        membre = serializer.validated_data["membre"]

        # Isolation tenant : la répétition ET le membre doivent appartenir
        # à la chorale du user (le mixin ne filtre que la lecture, pas les FK
        # d'un POST). 404 pour ne pas révéler l'existence d'autres chorales.
        chorale = getattr(request, "chorale", None)
        if chorale and (
            repetition.chorale_id != chorale.id or membre.chorale_id != chorale.id
        ):
            raise NotFound()

        presence, created = Presence.objects.update_or_create(
            repetition=repetition,
            membre=membre,
            defaults={
                "statut": serializer.validated_data["statut"],
                "motif": serializer.validated_data.get("motif", ""),
                "chorale": repetition.chorale,
            },
        )

        out = self.get_serializer(presence)
        return Response(
            out.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


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

    def get_queryset(self):
        """
        Confidentialité : seuls les valideurs (bureau / maître de chœur / super
        admin) voient toutes les demandes de la chorale. Un membre lambda ne voit
        que SES propres demandes — sinon il lirait les motifs d'absence des autres.
        """
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        groupes = set(user.groups.values_list("name", flat=True))
        if groupes & {"bureau", "maitre_choeur"}:
            return qs
        membre = getattr(user, "membre", None)
        return qs.filter(membre=membre) if membre is not None else qs.none()

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
        self._notifier_traitement(demande)

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
        self._notifier_traitement(demande)

        return Response({"detail": "Demande refusée."})

    @staticmethod
    def _notifier_traitement(demande):
        """Prévient le demandeur (in-app + email) que sa demande est traitée."""
        from notifications.services import notifier
        from notifications.models import Notification

        approuvee = demande.statut == PermissionRequest.StatutDemande.APPROUVEE
        periode = f"du {demande.date_debut:%d/%m/%Y} au {demande.date_fin:%d/%m/%Y}" \
            if demande.date_fin and demande.date_fin != demande.date_debut \
            else f"du {demande.date_debut:%d/%m/%Y}"
        notifier(
            demande.membre,
            type_notification=Notification.Type.PERMISSION,
            titre=f"Demande d'absence {'approuvée' if approuvee else 'refusée'}",
            message=f"Votre demande d'absence {periode} a été "
                    f"{'approuvée' if approuvee else 'refusée'}"
                    + (f" par {demande.traitee_par.nom_complet}." if demande.traitee_par else "."),
            lien="/presences/permissions",
            par_email=True,
        )

    def _bulk_traiter(self, request, nouveau_statut):
        """
        Traite en lot les demandes en_attente dont l'id figure dans
        {"ids": [...]}. Les demandes déjà traitées ou hors périmètre
        (isolation tenant via get_queryset) sont ignorées, pas bloquantes.
        """
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "Liste d'ids requise."}, status=status.HTTP_400_BAD_REQUEST)

        demandes = list(
            self.get_queryset().filter(
                pk__in=ids, statut=PermissionRequest.StatutDemande.EN_ATTENTE
            )
        )
        now = timezone.now()
        for d in demandes:
            d.statut = nouveau_statut
            d.traitee_par = request.user.membre
            d.date_traitement = now
        PermissionRequest.objects.bulk_update(demandes, ["statut", "traitee_par", "date_traitement"])
        for d in demandes:
            self._notifier_traitement(d)

        return Response({"detail": f"{len(demandes)} demande(s) traitée(s).", "count": len(demandes)})

    @action(detail=False, methods=["post"], url_path="bulk-approuver",
            permission_classes=[IsBureauOrMaitreChoeur])
    def bulk_approuver(self, request):
        """POST {"ids": [1,2,3]} → approuve chaque demande en attente du lot."""
        return self._bulk_traiter(request, PermissionRequest.StatutDemande.APPROUVEE)

    @action(detail=False, methods=["post"], url_path="bulk-refuser",
            permission_classes=[IsBureauOrMaitreChoeur])
    def bulk_refuser(self, request):
        """POST {"ids": [1,2,3]} → refuse chaque demande en attente du lot."""
        return self._bulk_traiter(request, PermissionRequest.StatutDemande.REFUSEE)
