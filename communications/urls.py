"""
ChoirManager — Communications URLs
====================================
Routes : /api/communications/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "communications"

router = DefaultRouter()
router.register(r"annonces", views.AnnonceViewSet, basename="annonce")

urlpatterns = [
    path("", include(router.urls)),
]
