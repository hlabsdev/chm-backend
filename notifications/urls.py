"""
ChoirManager — Notifications URLs
====================================
Routes : /api/notifications/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "notifications"

router = DefaultRouter()
router.register(r"", views.NotificationViewSet, basename="notification")

urlpatterns = [
    path("", include(router.urls)),
]
