"""
ChoirManager — Finances Views
================================
API REST pour la gestion financière : journal, campagnes, cotisations, paiements.
"""

from datetime import date

from django.db.models import Q, Sum
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import ChoraleFilterMixin, SoftDeleteMixin
from core.permissions import IsBureau, IsBureauOrTresorier

from .models import (
    CampagneCotisation,
    CategorieMouvement,
    Cotisation,
    Mouvement,
    PaiementCotisation,
)
from .serializers import (
    CampagneCotisationListSerializer,
    CategorieMouvementSerializer,
    CotisationSerializer,
    EtatCaisseSerializer,
    MouvementSerializer,
    PaiementCotisationSerializer,
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
    filterset_fields = ["sens", "categorie", "membre"]
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
                montant_du=campagne.montant_unitaire,
            )
            cotisations_creees.append(cotisation)

        return Response(
            {
                "detail": f"{len(cotisations_creees)} cotisations générées pour la campagne « {campagne.nom} ».",
                "nombre": len(cotisations_creees),
            },
            status=status.HTTP_201_CREATED,
        )


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
    permission_classes = [IsBureauOrTresorier]
    filterset_fields = ["campagne", "membre", "statut"]


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
