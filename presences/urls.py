"""
ChoirManager — Presences URLs
================================
Routes : /api/presences/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "presences"

router = DefaultRouter()
router.register(r"repetitions", views.RepetitionViewSet, basename="repetition")
router.register(r"pointages", views.PresenceViewSet, basename="presence")
router.register(r"permissions", views.PermissionRequestViewSet, basename="permission-request")

urlpatterns = [
    path("", include(router.urls)),
]
