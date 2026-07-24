"""
ChoirManager — Membres Serializers
====================================
Sérialiseurs DRF pour Pupitre, Poste, Membre, Mandat.
"""

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password as valider_mot_de_passe
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import InvitationChorale, Mandat, Membre, Poste, Pupitre


def _valider_mot_de_passe_drf(value: str) -> str:
    """
    Applique les validateurs Django (AUTH_PASSWORD_VALIDATORS : longueur,
    mots de passe trop communs, tout-numérique…) dans un serializer DRF —
    ils ne s'appliquent pas automatiquement hors des formulaires Django.
    """
    try:
        valider_mot_de_passe(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return value


# ---------------------------------------------------------------------------
# Groupe RBAC (lecture seule) — pour l'assignation aux postes
# ---------------------------------------------------------------------------

class GroupeSerializer(serializers.ModelSerializer):
    """Groupe Django RBAC assignable à un poste."""

    class Meta:
        model = Group
        fields = ["id", "name"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Pupitre
# ---------------------------------------------------------------------------

class PupitreSerializer(serializers.ModelSerializer):
    """Sérialiseur complet pour les pupitres."""
    nombre_membres = serializers.SerializerMethodField()

    class Meta:
        model = Pupitre
        fields = [
            "id", "nom", "categorie", "ordre",
            "nombre_membres", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_nombre_membres(self, obj) -> int:
        """Nombre de membres actifs dans ce pupitre."""
        return obj.membres.filter(is_deleted=False, statut="actif").count()


# ---------------------------------------------------------------------------
# Poste
# ---------------------------------------------------------------------------

class PosteSerializer(serializers.ModelSerializer):
    """Sérialiseur complet pour les postes."""
    groupes_noms = serializers.SlugRelatedField(
        source="groupes",
        many=True,
        read_only=True,
        slug_field="name",
    )
    # Écriture des groupes RBAC accordés par le poste (permissions Django).
    groupes_ids = serializers.PrimaryKeyRelatedField(
        source="groupes",
        many=True,
        write_only=True,
        required=False,
        queryset=Group.objects.all(),
    )
    titulaire_actuel = serializers.SerializerMethodField()

    class Meta:
        model = Poste
        fields = [
            "id", "nom", "description", "type_poste",
            "unique_actif", "pupitre_concerne",
            "groupes_noms", "groupes_ids", "titulaire_actuel",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_titulaire_actuel(self, obj) -> dict | None:
        """
        Retourne le titulaire actif du poste, si existant.
        Utilise le Prefetch `mandats_actifs_liste` posé par PosteViewSet
        (évite une requête par poste) ; requête directe en repli si le
        serializer est utilisé hors de ce contexte.
        """
        mandats = getattr(obj, "mandats_actifs_liste", None)
        if mandats is None:
            mandats = list(
                obj.mandats.filter(is_active=True).select_related("membre__user")[:1]
            )
        mandat = mandats[0] if mandats else None
        if mandat:
            return {
                "membre_id": mandat.membre.pk,
                "nom_complet": mandat.membre.nom_complet,
                "depuis": mandat.date_debut,
            }
        return None


# ---------------------------------------------------------------------------
# Mandat
# ---------------------------------------------------------------------------

class MandatSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les mandats avec validation métier."""
    membre_nom = serializers.CharField(
        source="membre.nom_complet", read_only=True
    )
    poste_nom = serializers.CharField(
        source="poste.nom", read_only=True
    )

    class Meta:
        model = Mandat
        fields = [
            "id", "membre", "membre_nom",
            "poste", "poste_nom",
            "date_debut", "date_fin", "is_active",
            "notes", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        """
        Valide les contraintes métier (unique_actif, dates).

        Cette vérification échoue vite pour l'utilisateur (400 avant toute
        écriture) mais NE FERME PAS la fenêtre de course : elle lit sans
        verrou, avant la transaction d'écriture. C'est create()/update()
        ci-dessous, sous verrou, qui a le dernier mot en cas de concurrence
        réelle — cf. Mandat.verrouiller_poste_pour_unicite().
        """
        poste = data.get("poste") or self.instance.poste if self.instance else None
        is_active = data.get("is_active", True)
        membre = data.get("membre") or self.instance.membre if self.instance else None

        if poste and is_active and poste.unique_actif:
            conflit = (
                Mandat.objects
                .filter(poste=poste, is_active=True)
                .exclude(pk=self.instance.pk if self.instance else None)
                .select_related("membre")
                .first()
            )
            if conflit:
                raise serializers.ValidationError(
                    f"Le poste « {poste.nom} » est déjà occupé par "
                    f"{conflit.membre.nom_complet}."
                )

        # Validation des dates
        date_debut = data.get("date_debut")
        date_fin = data.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({
                "date_fin": "La date de fin ne peut pas être antérieure à la date de début."
            })

        return data

    def _revalider_sous_verrou(self, poste, is_active, exclude_pk):
        """Répète la vérification de validate() APRÈS le verrou — seule autorité en cas de course."""
        if is_active and poste.unique_actif:
            conflit = (
                Mandat.objects
                .filter(poste=poste, is_active=True)
                .exclude(pk=exclude_pk)
                .select_related("membre")
                .first()
            )
            if conflit:
                raise serializers.ValidationError(
                    f"Le poste « {poste.nom} » est déjà occupé par "
                    f"{conflit.membre.nom_complet}."
                )

    @transaction.atomic
    def create(self, validated_data):
        poste = validated_data["poste"]
        Mandat.verrouiller_poste_pour_unicite(poste)
        self._revalider_sous_verrou(
            poste, validated_data.get("is_active", True), exclude_pk=None
        )
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        poste = validated_data.get("poste", instance.poste)
        Mandat.verrouiller_poste_pour_unicite(poste)
        self._revalider_sous_verrou(
            poste, validated_data.get("is_active", instance.is_active), exclude_pk=instance.pk
        )
        return super().update(instance, validated_data)


class MandatNestedSerializer(serializers.ModelSerializer):
    """Sérialiseur imbriqué (lecture seule) pour afficher dans le détail d'un membre."""
    poste_nom = serializers.CharField(source="poste.nom", read_only=True)
    poste_type = serializers.CharField(source="poste.type_poste", read_only=True)

    class Meta:
        model = Mandat
        fields = [
            "id", "poste", "poste_nom", "poste_type",
            "date_debut", "date_fin", "is_active",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Membre
# ---------------------------------------------------------------------------

class MembreListSerializer(serializers.ModelSerializer):
    """
    Sérialiseur léger pour les listes de membres.
    Optimisé pour minimiser les requêtes DB.
    """
    nom_complet = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    pupitre_nom = serializers.CharField(source="pupitre.nom", read_only=True, default=None)
    pupitre_categorie = serializers.CharField(source="pupitre.categorie", read_only=True, default=None)

    class Meta:
        model = Membre
        fields = [
            "id", "numero_membre", "nom_complet", "email",
            "pupitre", "pupitre_nom", "pupitre_categorie", "statut", "sexe",
            "date_adhesion", "telephone",
        ]
        read_only_fields = fields


class MembreCreateSerializer(serializers.ModelSerializer):
    """
    Création d'un membre par le bureau.

    Flux défini : le bureau saisit un identifiant de connexion + un mot de passe
    provisoire (à communiquer au membre, qui pourra le changer). Le compte User
    Django et le profil Membre sont créés atomiquement, et le `numero_membre`
    est auto-généré à partir du préfixe de la chorale.
    """
    username = serializers.CharField(write_only=True, max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(write_only=True, max_length=150)
    last_name = serializers.CharField(write_only=True, max_length=150)
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)

    numero_membre = serializers.CharField(read_only=True)
    nom_complet = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = Membre
        fields = [
            "id", "username", "password", "first_name", "last_name", "email",
            "pupitre", "statut", "sexe", "date_adhesion", "telephone",
            "numero_membre", "nom_complet",
        ]
        read_only_fields = ["id", "numero_membre", "nom_complet"]

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Cette adresse email est déjà utilisée.")
        return value

    def validate_password(self, value):
        return _valider_mot_de_passe_drf(value)

    @transaction.atomic
    def create(self, validated_data):
        # `chorale` est injectée par ChoraleFilterMixin.perform_create.
        chorale = validated_data.pop("chorale")
        user = User.objects.create_user(
            username=validated_data.pop("username"),
            password=validated_data.pop("password"),
            first_name=validated_data.pop("first_name"),
            last_name=validated_data.pop("last_name"),
            email=validated_data.pop("email", ""),
        )
        return Membre.objects.create(
            user=user,
            chorale=chorale,
            numero_membre=Membre.generer_numero(chorale),
            **validated_data,
        )


class MembreDetailSerializer(serializers.ModelSerializer):
    """
    Sérialiseur complet pour le détail d'un membre.
    Inclut les mandats actifs et l'historique.
    """
    # Champs User
    username = serializers.CharField(source="user.username", read_only=True)
    nom_complet = serializers.CharField(source="user.get_full_name", read_only=True)
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    email = serializers.EmailField(source="user.email")

    # Champs relationnels
    pupitre_nom = serializers.CharField(source="pupitre.nom", read_only=True, default=None)
    pupitre_categorie = serializers.CharField(source="pupitre.categorie", read_only=True, default=None)
    mandats_actifs = MandatNestedSerializer(many=True, read_only=True, source="mandats")
    groupes = serializers.SerializerMethodField()

    class Meta:
        model = Membre
        fields = [
            "id", "username", "numero_membre",
            "nom_complet", "first_name", "last_name", "email",
            "pupitre", "pupitre_nom", "pupitre_categorie", "statut", "sexe",
            "date_adhesion", "telephone", "photo", "notes",
            "mandats_actifs", "groupes",
            "is_deleted", "deleted_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "username", "numero_membre",
            "is_deleted", "deleted_at", "created_at", "updated_at",
        ]

    def get_groupes(self, obj) -> list[str]:
        """Groupes Django de l'utilisateur."""
        return list(obj.user.groups.values_list("name", flat=True))

    def update(self, instance, validated_data):
        """Met à jour les champs User et Membre ensemble."""
        user_data = validated_data.pop("user", {})

        # Mise à jour des champs User
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()

        # Mise à jour des champs Membre
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# InvitationChorale — gestion Bureau + inscription publique par code
# ---------------------------------------------------------------------------

class InvitationSerializer(serializers.ModelSerializer):
    """Gestion (Bureau) des codes d'invitation de sa chorale."""
    cree_par_nom = serializers.CharField(source="cree_par.nom_complet", read_only=True, default=None)
    pupitre_suggere_nom = serializers.CharField(source="pupitre_suggere.nom", read_only=True, default=None)
    est_valide = serializers.SerializerMethodField()

    class Meta:
        model = InvitationChorale
        fields = [
            "id", "code", "cree_par_nom", "pupitre_suggere", "pupitre_suggere_nom",
            "note", "is_active", "expire_le", "max_utilisations", "nombre_utilisations",
            "est_valide", "created_at",
        ]
        read_only_fields = ["id", "code", "cree_par_nom", "nombre_utilisations", "est_valide", "created_at"]

    def get_est_valide(self, obj) -> bool:
        return obj.est_valide()


class InvitationVerifierSerializer(serializers.Serializer):
    """Réponse publique de vérification d'un code (avant inscription)."""
    valide = serializers.BooleanField()
    chorale_nom = serializers.CharField(required=False)
    pupitre_suggere = serializers.CharField(required=False, allow_null=True)


class RejoindreInvitationSerializer(serializers.Serializer):
    """
    Auto-inscription publique via un code d'invitation généré par le Bureau
    d'une chorale précise. Remplace l'ancien endpoint ouvert (retiré) qui
    exigeait seulement de deviner un chorale_id séquentiel — ici, il faut
    connaître un code long, aléatoire, et volontairement partagé.
    """
    code = serializers.CharField(write_only=True)
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    telephone = serializers.CharField(max_length=25, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Cette adresse email est déjà utilisée.")
        return value

    def validate_password(self, value):
        return _valider_mot_de_passe_drf(value)

    def validate_code(self, value):
        code = value.strip().upper()
        try:
            invitation = InvitationChorale.objects.select_related("chorale").get(code=code)
        except InvitationChorale.DoesNotExist:
            raise serializers.ValidationError("Code d'invitation invalide.")
        if not invitation.est_valide():
            raise serializers.ValidationError("Ce code d'invitation n'est plus valide (expiré ou épuisé).")
        return code

    @transaction.atomic
    def create(self, validated_data):
        # Reverrouille et revalide sous transaction pour fermer toute fenêtre
        # de course entre deux inscriptions concurrentes sur un code à
        # usage limité (ex. max_utilisations=1).
        invitation = InvitationChorale.objects.select_for_update().select_related("chorale").get(
            code=validated_data["code"]
        )
        if not invitation.est_valide():
            raise serializers.ValidationError({"code": "Ce code d'invitation n'est plus valide."})

        chorale = invitation.chorale
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            email=validated_data.get("email", ""),
        )
        Membre.objects.create(
            user=user, chorale=chorale,
            numero_membre=Membre.generer_numero(chorale),
            date_adhesion=timezone.now().date(),
            statut=Membre.Statut.ACTIF,
            pupitre=invitation.pupitre_suggere,
            telephone=validated_data.get("telephone", ""),
            invitation_utilisee=invitation,
        )
        invitation.nombre_utilisations += 1
        invitation.save(update_fields=["nombre_utilisations", "updated_at"])

        return user
