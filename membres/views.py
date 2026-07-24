"""
ChoirManager — Membres Views (ViewSets DRF)
=============================================
API REST pour la gestion des pupitres, postes, membres et mandats.
Tous les ViewSets utilisent ChoraleFilterMixin pour l'isolation par chorale.
"""

from django.contrib.auth.models import Group
from django.db.models import Prefetch
from rest_framework import generics, viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.serializers import CustomTokenObtainPairSerializer
from core.mixins import ChoraleFilterMixin, SoftDeleteMixin
from core.permissions import IsBureau, IsBureauOrMaitreChoeur, IsMembreActif
from core.throttles import InvitationRejoindreThrottle, InvitationVerifierThrottle

from .filters import MembreFilter
from .models import InvitationChorale, Mandat, Membre, Poste, Pupitre, generer_code_invitation
from .serializers import (
    GroupeSerializer,
    InvitationSerializer,
    MandatSerializer,
    MembreCreateSerializer,
    MembreDetailSerializer,
    MembreListSerializer,
    PosteSerializer,
    PupitreSerializer,
    RejoindreInvitationSerializer,
)

# Groupes RBAC assignables à un poste (les groupes de base membre_actif /
# membre_honoraire sont gérés automatiquement par le statut, pas via les postes).
_GROUPES_ASSIGNABLES = ["bureau", "tresorier", "maitre_choeur", "chef_pupitre"]


class GroupeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Groupes RBAC assignables à un poste (permissions Django). Lecture réservée
    au bureau — sert à alimenter le formulaire de gestion des postes.
    Les groupes ne sont pas scopés chorale (partagés par la plateforme).
    """
    serializer_class = GroupeSerializer
    permission_classes = [IsBureau]
    pagination_class = None

    def get_queryset(self):
        return Group.objects.filter(name__in=_GROUPES_ASSIGNABLES).order_by("name")


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
        if self.action in ["list", "retrieve", "organigramme"]:
            return [permissions.IsAuthenticated()]
        return [IsBureau()]

    @action(detail=False, methods=["get"])
    def organigramme(self, request):
        """
        Organigramme de la chorale : postes pourvus et leurs titulaires actifs,
        groupés par type de poste. Lecture ouverte à tout membre (ne révèle que
        « qui occupe quel poste », pas les notes de mandat).
        """
        postes = (
            self.get_queryset()
            .select_related("pupitre_concerne")
            .prefetch_related(
                Prefetch(
                    "mandats",
                    queryset=Mandat.objects.filter(is_active=True).select_related("membre__user"),
                    to_attr="mandats_actifs_liste",
                )
            )
            .order_by("type_poste", "nom")
        )
        data = []
        for poste in postes:
            titulaires = [
                {
                    "membre_id": m.membre.pk,
                    "nom_complet": m.membre.nom_complet,
                    "depuis": m.date_debut,
                }
                for m in poste.mandats_actifs_liste
            ]
            if not titulaires:
                continue  # on ne montre que les postes effectivement pourvus
            data.append({
                "poste_id": poste.id,
                "nom": poste.nom,
                "type_poste": poste.type_poste,
                "type_poste_libelle": poste.get_type_poste_display(),
                "pupitre_concerne": poste.pupitre_concerne.nom if poste.pupitre_concerne_id else None,
                "titulaires": titulaires,
            })
        return Response(data)


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
        if self.action == "create":
            return MembreCreateSerializer
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


class InvitationViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Invitations — codes permettant à un choriste de rejoindre la chorale
    par auto-inscription. Gestion réservée au Bureau (outil interne, pas
    besoin d'être visible des choristes).

    GET    /api/membres/invitations/          → codes de la chorale
    POST   /api/membres/invitations/          → génère un nouveau code
    PATCH  /api/membres/invitations/{id}/     → désactiver, changer expiration…
    DELETE /api/membres/invitations/{id}/     → supprimer définitivement
    """
    queryset = InvitationChorale.objects.select_related("cree_par__user", "pupitre_suggere")
    serializer_class = InvitationSerializer
    permission_classes = [IsBureau]

    def perform_create(self, serializer):
        chorale = getattr(self.request, "chorale", None)
        membre = getattr(self.request.user, "membre", None)
        if not chorale:
            raise PermissionDenied("Vous devez être associé à une chorale pour créer une invitation.")

        code = generer_code_invitation()
        while InvitationChorale.objects.filter(code=code).exists():
            code = generer_code_invitation()

        serializer.save(chorale=chorale, cree_par=membre, code=code)


class InvitationVerifierView(APIView):
    """
    GET /api/membres/invitations/verifier/?code=XXXXXXXX
    Vérification publique (non authentifiée) d'un code avant inscription.
    Ne révèle rien d'autre que la validité et le nom de la chorale.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [InvitationVerifierThrottle]

    def get(self, request):
        code = (request.query_params.get("code") or "").strip().upper()
        invitation = (
            InvitationChorale.objects.select_related("chorale", "pupitre_suggere")
            .filter(code=code)
            .first()
        )
        if not invitation or not invitation.est_valide():
            return Response({"valide": False})
        return Response({
            "valide": True,
            "chorale_nom": invitation.chorale.nom,
            "pupitre_suggere": invitation.pupitre_suggere.nom if invitation.pupitre_suggere_id else None,
        })


class InvitationRejoindreView(generics.CreateAPIView):
    """
    POST /api/membres/invitations/rejoindre/
    Auto-inscription publique via un code d'invitation valide. Crée le User
    + Membre dans la chorale du code, puis connecte immédiatement (JWT),
    comme le faisait l'ancien flux d'inscription (mais scopé par un code
    long et aléatoire au lieu d'un chorale_id deviné).
    """
    serializer_class = RejoindreInvitationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [InvitationRejoindreThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token_serializer = CustomTokenObtainPairSerializer()
        token = token_serializer.get_token(user)

        return Response(
            {
                "detail": "Inscription réussie.",
                "access": str(token.access_token),
                "refresh": str(token),
            },
            status=status.HTTP_201_CREATED,
        )
