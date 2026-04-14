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
router.register(r"mandats", views.MandatViewSet, basename="mandat")
router.register(r"", views.MembreViewSet, basename="membre")

urlpatterns = [
    path("", include(router.urls)),
]
