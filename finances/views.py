"""
ChoirManager — Finances Views
================================
API REST pour la gestion financière : journal, campagnes, cotisations, paiements.
"""

from datetime import date

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import ChoraleFilterMixin, SoftDeleteMixin
from core.permissions import IsBureau, IsBureauOrTresorier

from .filters import MouvementFilter
from .models import (
    CampagneCotisation,
    CategorieMouvement,
    Cotisation,
    Mouvement,
    PaiementCotisation,
    TarifCotisation,
)
from .serializers import (
    CampagneCotisationListSerializer,
    CategorieMouvementSerializer,
    CotisationSerializer,
    EtatCaisseSerializer,
    MouvementSerializer,
    PaiementCotisationSerializer,
    TarifCotisationSerializer,
)


class CategorieMouvementViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """API Catégories de mouvement — Types de transactions."""
    queryset = CategorieMouvement.objects.all()
    serializer_class = CategorieMouvementSerializer
    permission_classes = [IsBureauOrTresorier]


class MouvementViewSet(SoftDeleteMixin, ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Journal de caisse — Mouvements financiers.

    Accès : Bureau ou Trésorier uniquement.

    Filtres :
    - ?sens=entree / ?sens=sortie
    - ?date_min=2025-01-01&date_max=2025-12-31
    - ?categorie=1
    - ?membre=5
    """
    queryset = Mouvement.objects.select_related(
        "categorie", "membre__user", "enregistre_par__user"
    )
    serializer_class = MouvementSerializer
    permission_classes = [IsBureauOrTresorier]
    filterset_class = MouvementFilter
    ordering_fields = ["date", "montant", "created_at"]

    def perform_create(self, serializer):
        """Enregistre automatiquement le membre connecté comme auteur."""
        chorale = getattr(self.request, "chorale", None)
        serializer.save(
            enregistre_par=self.request.user.membre,
            chorale=chorale,
        )


class CampagneCotisationViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Campagnes de cotisation — Définition des cotisations.

    Actions supplémentaires :
    POST /api/finances/campagnes/{id}/generer/  → génère les cotisations pour tous les membres actifs
    """
    queryset = CampagneCotisation.objects.all()
    serializer_class = CampagneCotisationListSerializer
    permission_classes = [IsBureauOrTresorier]
    filterset_fields = ["type_campagne", "is_active"]

    @action(detail=True, methods=["post"])
    def generer(self, request, pk=None):
        """
        Génère les cotisations individuelles pour tous les membres actifs
        de la chorale associée à cette campagne.
        """
        from membres.models import Membre

        campagne = self.get_object()

        # Récupérer les membres actifs de la chorale qui n'ont pas encore de cotisation
        membres_actifs = (
            Membre.objects
            .filter(chorale=campagne.chorale, statut="actif", is_deleted=False)
            .exclude(cotisations__campagne=campagne)
        )

        cotisations_creees = []
        for membre in membres_actifs:
            cotisation = Cotisation.objects.create(
                chorale=campagne.chorale,
                campagne=campagne,
                membre=membre,
                # Montant déduit des paliers (tarifs) de la campagne selon le
                # profil du membre ; ajustable ensuite ligne par ligne.
                montant_du=campagne.montant_pour(membre),
            )
            cotisations_creees.append(cotisation)

        return Response(
            {
                "detail": f"{len(cotisations_creees)} cotisations générées pour la campagne « {campagne.nom} ».",
                "nombre": len(cotisations_creees),
            },
            status=status.HTTP_201_CREATED,
        )


class TarifCotisationViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Tarifs (paliers) de cotisation.
    Ex. « Tenue femmes : 5000 » / « Tenue hommes : 4500 ».
    """
    queryset = TarifCotisation.objects.select_related("critere_pupitre")
    serializer_class = TarifCotisationSerializer
    permission_classes = [IsBureauOrTresorier]
    filterset_fields = ["campagne"]


class CotisationViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Cotisations — Suivi par membre et par campagne.

    Filtres :
    - ?campagne=1
    - ?membre=5
    - ?statut=en_attente
    """
    queryset = Cotisation.objects.select_related(
        "campagne", "membre__user"
    ).filter(is_deleted=False)
    serializer_class = CotisationSerializer
    filterset_fields = ["campagne", "membre", "statut"]

    def get_permissions(self):
        # Lecture : tout membre authentifié (mais restreinte aux siennes, cf.
        # get_queryset). Écriture : bureau ou trésorier.
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsBureauOrTresorier()]

    def get_queryset(self):
        """Un membre lambda ne voit que SES cotisations ; le staff voit tout."""
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        groupes = set(user.groups.values_list("name", flat=True))
        if groupes & {"bureau", "tresorier"}:
            return qs
        membre = getattr(user, "membre", None)
        return qs.filter(membre=membre) if membre is not None else qs.none()

    @action(detail=True, methods=["post"])
    def exonerer(self, request, pk=None):
        """Exonère un membre de cette cotisation (statut = exonéré)."""
        cotisation = self.get_object()
        cotisation.statut = Cotisation.StatutCotisation.EXONERE
        cotisation.save(update_fields=["statut", "updated_at"])
        return Response(CotisationSerializer(cotisation).data)

    def _cotisations_selection(self, request):
        """
        Résout la liste d'IDs demandée en cotisations réellement accessibles
        (isolation tenant incluse, via get_queryset). Les IDs absents/hors
        périmètre sont silencieusement ignorés — jamais une erreur 404 globale
        qui bloquerait le reste du lot.
        """
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return None
        return list(self.get_queryset().filter(pk__in=ids))

    @action(detail=False, methods=["post"], url_path="bulk-exonerer")
    def bulk_exonerer(self, request):
        """POST {"ids": [1,2,3]} → exonère chaque cotisation du lot."""
        cotisations = self._cotisations_selection(request)
        if cotisations is None:
            return Response({"detail": "Liste d'ids requise."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for c in cotisations:
                c.statut = Cotisation.StatutCotisation.EXONERE
            Cotisation.objects.bulk_update(cotisations, ["statut"])

        return Response({"detail": f"{len(cotisations)} cotisation(s) exonérée(s).", "count": len(cotisations)})

    @action(detail=False, methods=["post"], url_path="bulk-encaisser")
    def bulk_encaisser(self, request):
        """
        POST {"ids": [1,2,3]} → encaisse le solde restant de chaque cotisation
        du lot (crée un PaiementCotisation + Mouvement par cotisation, dans
        UNE transaction : soit tout est encaissé, soit rien ne l'est).
        """
        cotisations = self._cotisations_selection(request)
        if cotisations is None:
            return Response({"detail": "Liste d'ids requise."}, status=status.HTTP_400_BAD_REQUEST)

        cibles = [c for c in cotisations if c.reste_a_payer > 0]
        today = timezone.now().date().isoformat()
        created = []
        try:
            with transaction.atomic():
                for c in cibles:
                    serializer = PaiementCotisationSerializer(
                        data={
                            "cotisation": c.id,
                            "montant": str(c.reste_a_payer),
                            "date_paiement": today,
                        },
                        context={"request": request},
                    )
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    created.append(c.id)
        except Exception:
            return Response(
                {"detail": "Encaissement groupé impossible — aucune cotisation n'a été modifiée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": f"{len(created)} cotisation(s) encaissée(s).", "count": len(created)})


class PaiementCotisationViewSet(ChoraleFilterMixin, viewsets.ModelViewSet):
    """
    API Paiements de cotisation.

    Crée automatiquement un mouvement (entrée) dans le journal de caisse
    et met à jour le statut de la cotisation.
    """
    queryset = PaiementCotisation.objects.select_related(
        "cotisation__membre__user", "cotisation__campagne"
    )
    serializer_class = PaiementCotisationSerializer
    permission_classes = [IsBureauOrTresorier]
    filterset_fields = ["cotisation", "cotisation__membre"]

    def get_queryset(self):
        """Filtre par chorale via la cotisation."""
        qs = super().get_queryset()

        if self.request.user.is_superuser:
            return qs

        chorale = getattr(self.request, "chorale", None)
        if chorale:
            return qs.filter(cotisation__chorale=chorale)

        return qs.none()


class EtatCaisseView(APIView):
    """
    GET /api/finances/etat-caisse/
    Retourne un résumé financier pour une période donnée.

    Paramètres query :
    - date_debut (défaut: 1er janvier de l'année en cours)
    - date_fin (défaut: aujourd'hui)
    """
    permission_classes = [IsBureauOrTresorier]

    def get(self, request):
        chorale = getattr(request, "chorale", None)
        if not chorale and not request.user.is_superuser:
            return Response(
                {"detail": "Aucune chorale associée."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Période
        date_debut = request.query_params.get(
            "date_debut",
            date(date.today().year, 1, 1).isoformat()
        )
        date_fin = request.query_params.get(
            "date_fin",
            date.today().isoformat()
        )

        # Filtrer les mouvements
        mouvements_qs = Mouvement.objects.filter(
            is_deleted=False,
            date__gte=date_debut,
            date__lte=date_fin,
        )

        if chorale:
            mouvements_qs = mouvements_qs.filter(chorale=chorale)

        # Calculs
        entrees = mouvements_qs.filter(sens="entree").aggregate(
            total=Sum("montant")
        )["total"] or 0

        sorties = mouvements_qs.filter(sens="sortie").aggregate(
            total=Sum("montant")
        )["total"] or 0

        data = {
            "total_entrees": entrees,
            "total_sorties": sorties,
            "solde": entrees - sorties,
            "nombre_mouvements": mouvements_qs.count(),
            "periode_debut": date_debut,
            "periode_fin": date_fin,
        }

        serializer = EtatCaisseSerializer(data)
        return Response(serializer.data)
