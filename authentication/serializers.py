"""
ChoirManager — Authentication Serializers
==========================================
Sérialiseurs pour le JWT et le profil utilisateur.

Le CustomTokenObtainPairSerializer enrichit le payload JWT avec
les informations du Membre et de la Chorale pour que le frontend
Angular puisse piloter l'affichage sans requêtes supplémentaires.

NOTE : il n'existe volontairement pas d'auto-inscription publique.
Un membre est toujours créé par le Bureau de sa chorale (POST
/api/membres/, IsBureau) ou par l'opérateur de la plateforme lors du
provisionnement d'une nouvelle chorale (cf.
core/management/commands/provision_chorale.py) — jamais par la
personne elle-même sans validation.
"""

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Enrichit le payload JWT avec les données Membre et Chorale.
    Refuse la connexion si la chorale du membre est suspendue (is_active=False).

    Payload résultant :
    {
        "user_id": 42,
        "membre_id": 15,
        "chorale_id": 1,
        "chorale_prefix": "LVO",
        "chorale_nom": "Les Voix d'Or",
        "nom_complet": "Jean Dupont",
        "groups": ["membre_actif", "bureau"],
        "email": "jean@example.com"
    }
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        membre = getattr(self.user, "membre", None)
        if membre is not None and not membre.chorale.is_active:
            raise AuthenticationFailed(
                "L'espace de votre chorale est actuellement suspendu. "
                "Contactez l'administrateur de la plateforme."
            )
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Données utilisateur de base
        token["email"] = user.email
        token["first_name"] = user.first_name
        token["last_name"] = user.last_name
        token["nom_complet"] = user.get_full_name()
        token["is_superuser"] = user.is_superuser

        # Groupes / rôles
        token["groups"] = list(
            user.groups.values_list("name", flat=True)
        )

        # Données Membre et Chorale
        membre = getattr(user, "membre", None)
        if membre:
            token["membre_id"] = membre.pk
            token["numero_membre"] = membre.numero_membre
            token["chorale_id"] = membre.chorale_id
            token["chorale_prefix"] = membre.chorale.prefix
            token["chorale_nom"] = membre.chorale.nom
            token["chorale_currency"] = membre.chorale.currency
        else:
            token["membre_id"] = None
            token["chorale_id"] = None

        return token


class ChangerMotDePasseSerializer(serializers.Serializer):
    """
    Changement de mot de passe par l'utilisateur connecté.
    Exige l'ancien mot de passe (pas de reset ici — un membre qui a perdu
    son mot de passe passe par le Bureau, qui peut lui en refixer un).
    """
    ancien = serializers.CharField(write_only=True)
    nouveau = serializers.CharField(write_only=True)

    def validate_ancien(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("L'ancien mot de passe est incorrect.")
        return value

    def validate_nouveau(self, value):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(value, user=self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["nouveau"])
        user.save(update_fields=["password"])
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la lecture/modification du profil connecté."""
    membre_id = serializers.IntegerField(source="membre.pk", read_only=True)
    numero_membre = serializers.CharField(source="membre.numero_membre", read_only=True)
    chorale_nom = serializers.CharField(source="membre.chorale.nom", read_only=True)
    pupitre = serializers.CharField(source="membre.pupitre.nom", read_only=True, default=None)
    statut = serializers.CharField(source="membre.statut", read_only=True)
    telephone = serializers.CharField(source="membre.telephone", required=False)
    groups = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name"
    )

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "membre_id", "numero_membre", "chorale_nom",
            "pupitre", "statut", "telephone", "groups",
        ]
        read_only_fields = ["id", "username"]
