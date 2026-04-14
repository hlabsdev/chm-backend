"""
ChoirManager — Finances URLs
================================
Routes : /api/finances/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "finances"

router = DefaultRouter()
router.register(r"categories", views.CategorieMouvementViewSet, basename="categorie")
router.register(r"mouvements", views.MouvementViewSet, basename="mouvement")
router.register(r"campagnes", views.CampagneCotisationViewSet, basename="campagne")
router.register(r"cotisations", views.CotisationViewSet, basename="cotisation")
router.register(r"paiements", views.PaiementCotisationViewSet, basename="paiement")

urlpatterns = [
    # État de caisse (vue non-ViewSet)
    path("etat-caisse/", views.EtatCaisseView.as_view(), name="etat-caisse"),

    # ViewSets
    path("", include(router.urls)),
]
