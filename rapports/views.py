"""
ChoirManager — Rapports Views
================================
Endpoints de rapports agrégés, scopés à la chorale du user connecté.

Chaque rapport renvoie du JSON par défaut, ou un fichier via ?format=pdf
(WeasyPrint) ou ?format=csv. La couche métier vit dans services.py et la
mise en forme des exports dans exports.py — ces vues ne font qu'orchestrer
permissions + période + format.

Permissions :
- financier : bureau OU trésorier (données sensibles) ;
- présences / effectifs / répertoire : bureau OU maître de chœur.
"""

from datetime import datetime

from django.http import HttpResponse
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsBureauOrMaitreChoeur, IsBureauOrTresorier

from . import exports, services


def _parse_date(valeur):
    if not valeur:
        return None
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class _BaseRapportView(APIView):
    """
    Résout la chorale du contexte (jamais celle d'un autre tenant), calcule
    le rapport via services.py, et le restitue au format demandé.

    Les sous-classes définissent `nom_rapport` et `calculer(chorale, request)`.
    """
    nom_rapport: str = ""

    def get_chorale(self, request):
        chorale = getattr(request, "chorale", None)
        if not chorale:
            # Superuser sans chorale : pas de rapport possible (aucun tenant ciblé).
            raise PermissionDenied("Aucune chorale associée à ce compte.")
        return chorale

    def calculer(self, chorale, request) -> dict:  # pragma: no cover - override
        raise NotImplementedError

    def get(self, request):
        chorale = self.get_chorale(request)
        data = self.calculer(chorale, request)
        return self._restituer(request, chorale, data)

    def _restituer(self, request, chorale, data):
        # Param `export` et non `format` : ce dernier est réservé par DRF
        # pour la négociation de contenu (déclencherait un 404 si inconnu).
        fmt = request.query_params.get("export", "json").lower()

        if fmt == "csv":
            contenu = exports.rapport_vers_csv(self.nom_rapport, data)
            response = HttpResponse(contenu, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{exports.nom_fichier(self.nom_rapport, "csv")}"'
            return response

        if fmt == "pdf":
            try:
                pdf = exports.rapport_vers_pdf(self.nom_rapport, data, chorale)
            except exports.PdfIndisponible:
                return Response(
                    {"detail": "Génération PDF indisponible sur le serveur "
                               "(dépendances système WeasyPrint manquantes). "
                               "Utilisez l'export CSV en attendant."},
                    status=503,
                )
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{exports.nom_fichier(self.nom_rapport, "pdf")}"'
            return response

        return Response(data)


class RapportFinancierView(_BaseRapportView):
    permission_classes = [IsBureauOrTresorier]
    nom_rapport = "financier"

    def calculer(self, chorale, request):
        return services.rapport_financier(
            chorale,
            _parse_date(request.query_params.get("date_debut")),
            _parse_date(request.query_params.get("date_fin")),
        )


class RapportPresencesView(_BaseRapportView):
    permission_classes = [IsBureauOrMaitreChoeur]
    nom_rapport = "presences"

    def calculer(self, chorale, request):
        return services.rapport_presences(
            chorale,
            _parse_date(request.query_params.get("date_debut")),
            _parse_date(request.query_params.get("date_fin")),
        )


class RapportEffectifsView(_BaseRapportView):
    permission_classes = [IsBureauOrMaitreChoeur]
    nom_rapport = "effectifs"

    def calculer(self, chorale, request):
        return services.rapport_effectifs(chorale)


class RapportRepertoireView(_BaseRapportView):
    permission_classes = [IsBureauOrMaitreChoeur]
    nom_rapport = "repertoire"

    def calculer(self, chorale, request):
        return services.rapport_repertoire(chorale)
