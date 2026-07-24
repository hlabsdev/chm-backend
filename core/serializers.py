"""
ChoirManager — Core Serializers
==================================
"""

from rest_framework import serializers

from .models import DemandeChorale


class DemandeChoraleCreateSerializer(serializers.ModelSerializer):
    """
    Formulaire public de demande d'adhésion d'une nouvelle chorale.

    Volontairement minimal : seuls les champs qu'un demandeur externe doit
    fournir sont exposés (jamais statut/prefix_attribue/notes_internes, qui
    sont du ressort de la modération). Un champ honeypot (`site_web`) piège
    les robots basiques — doit rester vide, sinon la requête est silencieusement
    ignorée côté vue (pas d'erreur qui renseignerait un bot sur le piège).
    """
    # Honeypot : jamais rempli par un humain (champ masqué côté formulaire).
    site_web = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = DemandeChorale
        fields = [
            "id", "nom_chorale", "prefix_souhaite", "ville_pays",
            "contact_nom", "contact_email", "contact_telephone", "message",
            "site_web", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_contact_email(self, value):
        # Anti-spam léger : pas deux demandes en attente pour le même email.
        if DemandeChorale.objects.filter(
            contact_email__iexact=value, statut=DemandeChorale.Statut.EN_ATTENTE
        ).exists():
            raise serializers.ValidationError(
                "Une demande est déjà en attente de traitement pour cet email."
            )
        return value

    def validate_nom_chorale(self, value):
        if DemandeChorale.objects.filter(
            nom_chorale__iexact=value, statut=DemandeChorale.Statut.EN_ATTENTE
        ).exists():
            raise serializers.ValidationError(
                "Une demande est déjà en attente de traitement pour ce nom de chorale."
            )
        return value
