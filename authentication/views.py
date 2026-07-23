"""
ChoirManager — Authentication Views
=====================================
Endpoints d'authentification : login JWT, profil.
"""

from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    CustomTokenObtainPairSerializer,
    UserProfileSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Authentification et obtention du token JWT enrichi.
    """
    serializer_class = CustomTokenObtainPairSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/auth/profile/  → Voir le profil du membre connecté.
    PATCH /api/auth/profile/ → Modifier les informations éditables.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
