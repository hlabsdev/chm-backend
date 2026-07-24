"""
ChoirManager — Core Admin
===========================
Enregistrement de Chorale et de la modération des demandes d'adhésion.

Chorale : c'est l'écran permettant à un superuser de consulter/ajuster une
chorale sans passer par le shell. La création proprement dite (avec ses
postes, pupitres et son premier compte Bureau) passe par
`core.services.provisionner_chorale`, soit via `manage.py provision_chorale`,
soit via l'approbation d'une DemandeChorale ci-dessous.

DemandeChorale : c'est ICI que se fait la modération anti-abus des demandes
publiques d'adhésion — jamais de provisionnement automatique depuis un
formulaire public. L'opérateur renseigne le préfixe attribué puis lance
l'action « Approuver et provisionner » (ou « Rejeter »).
"""

from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify

from .models import Chorale, DemandeChorale
from .services import ProvisionnementError, provisionner_chorale


@admin.register(Chorale)
class ChoraleAdmin(admin.ModelAdmin):
    list_display = ["nom", "prefix", "currency", "is_active", "date_creation", "created_at"]
    list_filter = ["is_active", "currency"]
    search_fields = ["nom", "prefix", "email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(DemandeChorale)
class DemandeChoraleAdmin(admin.ModelAdmin):
    list_display = ["nom_chorale", "contact_nom", "contact_email", "statut", "created_at", "date_traitement"]
    list_filter = ["statut"]
    search_fields = ["nom_chorale", "contact_nom", "contact_email", "ville_pays"]
    readonly_fields = [
        "nom_chorale", "prefix_souhaite", "ville_pays", "contact_nom", "contact_email",
        "contact_telephone", "message", "adresse_ip", "created_at", "updated_at",
        "statut", "chorale_creee", "date_traitement",
    ]
    fieldsets = (
        ("Demande (soumise par le contact)", {
            "fields": (
                "nom_chorale", "prefix_souhaite", "ville_pays",
                "contact_nom", "contact_email", "contact_telephone", "message",
                "adresse_ip", "created_at",
            ),
        }),
        ("À compléter avant approbation", {
            "fields": ("prefix_attribue", "devise", "notes_internes"),
        }),
        ("Modération", {
            "fields": ("statut", "chorale_creee", "date_traitement"),
        }),
    )
    actions = ["approuver_et_provisionner", "rejeter"]

    def has_add_permission(self, request):
        # Les demandes n'existent que via le formulaire public.
        return False

    @admin.action(description="Approuver et provisionner la/les chorale(s) sélectionnée(s)")
    def approuver_et_provisionner(self, request, queryset):
        traitees, ignorees = 0, 0
        for demande in queryset:
            if demande.statut != DemandeChorale.Statut.EN_ATTENTE:
                ignorees += 1
                continue
            if not demande.prefix_attribue:
                self.message_user(
                    request,
                    f"« {demande.nom_chorale} » : renseignez d'abord le préfixe attribué "
                    f"(ouvrez la demande, remplissez « Préfixe attribué », enregistrez, puis relancez l'action).",
                    level=messages.ERROR,
                )
                ignorees += 1
                continue

            prenom, _, nom = demande.contact_nom.strip().partition(" ")
            username = _identifiant_disponible(prenom or demande.contact_nom, nom)
            try:
                chorale, admin_user, password, genere = provisionner_chorale(
                    nom=demande.nom_chorale, prefix=demande.prefix_attribue, currency=demande.devise,
                    admin_username=username, admin_email=demande.contact_email,
                    admin_first_name=prenom or demande.contact_nom, admin_last_name=nom or "Bureau",
                )
            except ProvisionnementError as exc:
                self.message_user(request, f"« {demande.nom_chorale} » : {exc}", level=messages.ERROR)
                ignorees += 1
                continue

            demande.statut = DemandeChorale.Statut.APPROUVEE
            demande.chorale_creee = chorale
            demande.date_traitement = timezone.now()
            demande.save(update_fields=["statut", "chorale_creee", "date_traitement", "updated_at"])

            # Email au contact (pas encore de compte → pas d'in-app). Jamais
            # le mot de passe par email : l'opérateur le transmet par un canal
            # direct (téléphone, message) — le mail ne contient que l'identifiant.
            from notifications.services import envoyer_email_externe
            envoyer_email_externe(
                demande.contact_email,
                f"Votre chorale « {chorale.nom} » est prête",
                f"Bonjour {demande.contact_nom},\n\n"
                f"Votre demande d'adhésion à ChoirManager a été approuvée : "
                f"l'espace de « {chorale.nom} » est créé.\n\n"
                f"Votre identifiant de connexion : {admin_user.username}\n"
                f"Votre mot de passe vous sera transmis séparément par notre équipe.\n\n"
                f"À très vite,\nL'équipe ChoirManager",
            )

            traitees += 1
            self.message_user(
                request,
                f"« {chorale.nom} » provisionnée. Compte Bureau : {admin_user.username}"
                + (f" / mot de passe généré : {password} (à transmettre puis faire changer)." if genere else "."),
                level=messages.SUCCESS,
            )

        if traitees:
            self.message_user(request, f"{traitees} demande(s) provisionnée(s).", level=messages.SUCCESS)
        if ignorees:
            self.message_user(request, f"{ignorees} demande(s) ignorée(s) (déjà traitée ou incomplète).", level=messages.WARNING)

    @admin.action(description="Rejeter la/les demande(s) sélectionnée(s)")
    def rejeter(self, request, queryset):
        from notifications.services import envoyer_email_externe

        en_attente = list(queryset.filter(statut=DemandeChorale.Statut.EN_ATTENTE))
        nb = queryset.filter(statut=DemandeChorale.Statut.EN_ATTENTE).update(
            statut=DemandeChorale.Statut.REJETEE, date_traitement=timezone.now(),
        )
        for demande in en_attente:
            envoyer_email_externe(
                demande.contact_email,
                "Votre demande d'adhésion à ChoirManager",
                f"Bonjour {demande.contact_nom},\n\n"
                f"Après examen, nous ne pouvons pas donner suite à la demande "
                f"d'adhésion de « {demande.nom_chorale} » pour le moment.\n"
                f"Vous pouvez nous recontacter pour plus d'informations.\n\n"
                f"L'équipe ChoirManager",
            )
        self.message_user(request, f"{nb} demande(s) rejetée(s).", level=messages.SUCCESS)



def _identifiant_disponible(prenom: str, nom: str) -> str:
    """Génère un username disponible à partir prénom.nom, avec suffixe numérique si pris."""
    base = slugify(f"{prenom}.{nom}".strip(".")) or "bureau"
    candidat = base
    i = 1
    while User.objects.filter(username=candidat).exists():
        i += 1
        candidat = f"{base}{i}"
    return candidat
