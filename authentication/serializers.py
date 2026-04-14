"""
ChoirManager — Authentication Serializers
==========================================
Sérialiseurs pour le JWT, l'inscription et le profil utilisateur.

Le CustomTokenObtainPairSerializer enrichit le payload JWT avec
les informations du Membre et de la Chorale pour que le frontend
Angular puisse piloter l'affichage sans requêtes supplémentaires.
"""

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from membres.models import Membre


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Enrichit le payload JWT avec les données Membre et Chorale.

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
        else:
            token["membre_id"] = None
            token["chorale_id"] = None

        return token


class RegisterSerializer(serializers.Serializer):
    """
    Inscription d'un nouveau membre.
    Crée un User Django + un Membre en une seule transaction atomique.

    Champs requis : username, email, password, first_name, last_name,
                    chorale_id, date_adhesion
    Champs optionnels : pupitre_id, telephone
    """
    # User fields
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)

    # Membre fields
    chorale_id = serializers.IntegerField()
    date_adhesion = serializers.DateField()
    pupitre_id = serializers.IntegerField(required=False, allow_null=True)
    telephone = serializers.CharField(max_length=25, required=False, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "Ce nom d'utilisateur est déjà pris."
            )
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Cette adresse email est déjà utilisée."
            )
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({
                "password_confirm": "Les mots de passe ne correspondent pas."
            })

        # Vérifier que la chorale existe
        from core.models import Chorale
        if not Chorale.objects.filter(pk=data["chorale_id"], is_active=True).exists():
            raise serializers.ValidationError({
                "chorale_id": "Chorale introuvable ou inactive."
            })

        return data

    @transaction.atomic
    def create(self, validated_data):
        from core.models import Chorale

        # Créer le User Django
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
        )

        # Récupérer la chorale
        chorale = Chorale.objects.get(pk=validated_data["chorale_id"])

        # Générer le numéro de membre
        numero = Membre.generer_numero(chorale)

        # Créer le Membre
        membre = Membre.objects.create(
            user=user,
            chorale=chorale,
            numero_membre=numero,
            date_adhesion=validated_data["date_adhesion"],
            pupitre_id=validated_data.get("pupitre_id"),
            telephone=validated_data.get("telephone", ""),
        )

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
