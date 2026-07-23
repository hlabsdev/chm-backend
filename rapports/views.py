"""
ChoirManager — Rapports Views
================================
Endpoints de rapports agrégés, scopés à la chorale du user connecté.

Chaque rapport renvoie du JSON par défaut. Les exports (PDF, CSV) seront
branchés au segment B via le paramètre ?format=. La couche métier vit dans
services.py — ces vues ne font qu'orchestrer permissions + période + format.

Permissions :
- financier : bureau OU trésorier (données sensibles) ;
- présences / effectifs / répertoire : bureau OU maître de chœur.
"""

from datetime import datetime

from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsBureauOrMaitreChoeur, IsBureauOrTresorier

from . import services


def _parse_date(valeur):
    if not valeur:
        return None
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class _BaseRapportView(APIView):
    """
    Résout la chorale du contexte (jamais celle d'un autre tenant) et
    délègue le calcul à une fonction de services.py.
    """

    def get_chorale(self, request):
        chorale = getattr(request, "chorale", None)
        if not chorale:
            # Superuser sans chorale : pas de rapport possible (aucun tenant ciblé).
            raise PermissionDenied("Aucune chorale associée à ce compte.")
        return chorale


class RapportFinancierView(_BaseRapportView):
    permission_classes = [IsBureauOrTresorier]

    def get(self, request):
        chorale = self.get_chorale(request)
        data = services.rapport_financier(
            chorale,
            _parse_date(request.query_params.get("date_debut")),
            _parse_date(request.query_params.get("date_fin")),
        )
        return Response(data)


class RapportPresencesView(_BaseRapportView):
    permission_classes = [IsBureauOrMaitreChoeur]

    def get(self, request):
        chorale = self.get_chorale(request)
        data = services.rapport_presences(
            chorale,
            _parse_date(request.query_params.get("date_debut")),
            _parse_date(request.query_params.get("date_fin")),
        )
        return Response(data)


class RapportEffectifsView(_BaseRapportView):
    permission_classes = [IsBureauOrMaitreChoeur]

    def get(self, request):
        chorale = self.get_chorale(request)
        return Response(services.rapport_effectifs(chorale))


class RapportRepertoireView(_BaseRapportView):
    permission_classes = [IsBureauOrMaitreChoeur]

    def get(self, request):
        chorale = self.get_chorale(request)
        return Response(services.rapport_repertoire(chorale))
