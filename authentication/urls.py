"""
ChoirManager — Authentication URLs
====================================
Routes : /api/auth/
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = "authentication"

urlpatterns = [
    # JWT
    path("login/", views.CustomTokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # Inscription
    path("register/", views.RegisterView.as_view(), name="register"),

    # Profil
    path("profile/", views.ProfileView.as_view(), name="profile"),
]
