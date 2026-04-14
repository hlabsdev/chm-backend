"""
ChoirManager — Musique URLs
==============================
Routes : /api/musique/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "musique"

router = DefaultRouter()
router.register(r"chants", views.ChantViewSet, basename="chant")
router.register(r"partitions", views.PartitionViewSet, basename="partition")
router.register(r"seances-chants", views.SeanceChantViewSet, basename="seance-chant")

urlpatterns = [
    path("", include(router.urls)),
]
