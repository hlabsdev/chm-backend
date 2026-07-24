"""
ChoirManager — Membres URLs
==============================
Routes : /api/membres/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "membres"

router = DefaultRouter()
router.register(r"pupitres", views.PupitreViewSet, basename="pupitre")
router.register(r"postes", views.PosteViewSet, basename="poste")
router.register(r"groupes", views.GroupeViewSet, basename="groupe")
router.register(r"mandats", views.MandatViewSet, basename="mandat")
router.register(r"invitations", views.InvitationViewSet, basename="invitation")
router.register(r"", views.MembreViewSet, basename="membre")

urlpatterns = [
    # Routes publiques explicites AVANT le router : sinon le pattern détail
    # du router (`invitations/<pk>/`) capturerait "verifier"/"rejoindre"
    # comme un pk.
    path("invitations/verifier/", views.InvitationVerifierView.as_view(), name="invitation-verifier"),
    path("invitations/rejoindre/", views.InvitationRejoindreView.as_view(), name="invitation-rejoindre"),
    path("", include(router.urls)),
]
