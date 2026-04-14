"""
ChoirManager — Authentication Views
=====================================
Endpoints d'authentification : login JWT, inscription, profil.
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserProfileSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Authentification et obtention du token JWT enrichi.
    """
    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Inscription d'un nouveau membre (User + Membre en transaction atomique).
    """
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Générer le token JWT pour le nouvel utilisateur
        token_serializer = CustomTokenObtainPairSerializer()
        token = token_serializer.get_token(user)

        return Response(
            {
                "message": "Inscription réussie.",
                "access": str(token.access_token),
                "refresh": str(token),
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/auth/profile/  → Voir le profil du membre connecté.
    PATCH /api/auth/profile/ → Modifier les informations éditables.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
