"""
ChoirManager — Authentication Views
=====================================
Endpoints d'authentification : login JWT, profil, changement de mot de passe.
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    ChangerMotDePasseSerializer,
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


class ChangerMotDePasseView(APIView):
    """
    POST /api/auth/changer-mot-de-passe/  {ancien, nouveau}
    Changement de mot de passe par l'utilisateur connecté (validateurs
    Django appliqués). Les tokens JWT déjà émis restent valides jusqu'à
    expiration (pas de blacklist au stade MVP).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangerMotDePasseSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Mot de passe modifié."}, status=status.HTTP_200_OK)
