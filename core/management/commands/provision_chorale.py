"""
ChoirManager — Provisionnement d'une nouvelle chorale
=========================================================
C'est aujourd'hui la SEULE voie officielle pour qu'une nouvelle chorale
rejoigne la plateforme (MVP : pas d'auto-inscription publique, cf.
authentication/serializers.py). L'opérateur de la plateforme exécute
cette commande, puis transmet les identifiants du premier compte Bureau
à la chorale cliente.

Crée en une transaction :
- la Chorale ;
- ses pupitres standards (Soprano, Alto, Ténor, Basse) ;
- ses postes standards (Bureau, Trésorier, Maître de chœur…) liés aux
  groupes Django RBAC ;
- ses catégories de mouvements financiers standards ;
- le premier compte utilisateur, membre « Président », avec un mandat
  actif (donc immédiatement dans le groupe `bureau`).

Sans cette commande, une Chorale créée « à la main » (shell, admin) est
inerte : aucun poste, aucun pupitre, personne pour s'y connecter.
"""

import secrets
import string

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Chorale
from finances.models import CategorieMouvement
from membres.models import Mandat, Membre, Poste, Pupitre

PUPITRES_STANDARDS = [
    {"nom": "Soprano", "categorie": "soprano", "ordre": 1},
    {"nom": "Alto", "categorie": "alto", "ordre": 2},
    {"nom": "Ténor", "categorie": "tenor", "ordre": 3},
    {"nom": "Basse", "categorie": "basse", "ordre": 4},
]

POSTES_STANDARDS = [
    {"nom": "Président", "type_poste": "bureau", "unique_actif": True, "groupes": ["bureau"]},
    {"nom": "Vice-Président", "type_poste": "bureau", "unique_actif": True, "groupes": ["bureau"]},
    {"nom": "Secrétaire Général", "type_poste": "bureau", "unique_actif": True, "groupes": ["bureau"]},
    {"nom": "Trésorier", "type_poste": "bureau", "unique_actif": True, "groupes": ["bureau", "tresorier"]},
    {"nom": "Commissaire aux comptes", "type_poste": "bureau", "unique_actif": True, "groupes": ["bureau"]},
    {"nom": "Maître de chœur Principal", "type_poste": "direction", "unique_actif": True, "groupes": ["maitre_choeur"]},
    {"nom": "Maître de chœur Suppléant", "type_poste": "direction", "unique_actif": False, "groupes": ["maitre_choeur"]},
    {"nom": "Chef de pupitre", "type_poste": "technique", "unique_actif": False, "groupes": ["chef_pupitre"]},
]

CATEGORIES_MOUVEMENT_STANDARDS = [
    {"nom": "Cotisation", "type_mouvement": "entree"},
    {"nom": "Don", "type_mouvement": "entree"},
    {"nom": "Subvention", "type_mouvement": "entree"},
    {"nom": "Vente (concert, CD…)", "type_mouvement": "entree"},
    {"nom": "Autre entrée", "type_mouvement": "entree"},
    {"nom": "Location salle", "type_mouvement": "sortie"},
    {"nom": "Transport", "type_mouvement": "sortie"},
    {"nom": "Achat matériel", "type_mouvement": "sortie"},
    {"nom": "Restauration", "type_mouvement": "sortie"},
    {"nom": "Impression / Photocopie", "type_mouvement": "sortie"},
    {"nom": "Autre sortie", "type_mouvement": "sortie"},
]

# Groupes RBAC globaux (partagés par toutes les chorales, cf. 0002_data_bootstrap).
GROUPES_RBAC = ["membre_actif", "membre_honoraire", "bureau", "tresorier", "maitre_choeur", "chef_pupitre"]


def _generer_mot_de_passe() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(14))


class Command(BaseCommand):
    help = (
        "Provisionne une nouvelle chorale : Chorale + pupitres/postes/catégories "
        "standards + premier compte Bureau (Président)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--nom", required=True, help="Nom de la chorale (unique).")
        parser.add_argument("--prefix", required=True, help="Préfixe matricule, 5 caractères max (unique).")
        parser.add_argument(
            "--currency", default=Chorale.Monnaie.XOF,
            choices=[c[0] for c in Chorale.Monnaie.choices],
            help="Devise de gestion (défaut : XOF).",
        )
        parser.add_argument("--admin-username", required=True, help="Identifiant du premier compte Bureau.")
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--admin-first-name", required=True)
        parser.add_argument("--admin-last-name", required=True)
        parser.add_argument(
            "--admin-password", default=None,
            help="Mot de passe du premier compte. Si omis, un mot de passe aléatoire est généré et affiché une seule fois.",
        )

    def handle(self, *args, **options):
        nom = options["nom"].strip()
        prefix = options["prefix"].strip().upper()

        if Chorale.objects.filter(nom__iexact=nom).exists():
            raise CommandError(f"Une chorale nommée « {nom} » existe déjà.")
        if Chorale.objects.filter(prefix__iexact=prefix).exists():
            raise CommandError(f"Le préfixe « {prefix} » est déjà utilisé par une autre chorale.")
        if User.objects.filter(username=options["admin_username"]).exists():
            raise CommandError(f"Le nom d'utilisateur « {options['admin_username']} » est déjà pris.")

        password = options["admin_password"] or _generer_mot_de_passe()
        mot_de_passe_genere = options["admin_password"] is None

        with transaction.atomic():
            chorale = Chorale.objects.create(
                nom=nom, prefix=prefix, currency=options["currency"],
                date_creation=timezone.now().date(),
            )

            groupes = {n: Group.objects.get_or_create(name=n)[0] for n in GROUPES_RBAC}

            for data in PUPITRES_STANDARDS:
                Pupitre.objects.get_or_create(
                    chorale=chorale, nom=data["nom"],
                    defaults={"categorie": data["categorie"], "ordre": data["ordre"]},
                )

            postes = {}
            for data in POSTES_STANDARDS:
                poste = Poste.objects.create(
                    chorale=chorale, nom=data["nom"],
                    type_poste=data["type_poste"], unique_actif=data["unique_actif"],
                )
                poste.groupes.set([groupes[g] for g in data["groupes"]])
                postes[data["nom"]] = poste

            for data in CATEGORIES_MOUVEMENT_STANDARDS:
                CategorieMouvement.objects.get_or_create(
                    chorale=chorale, nom=data["nom"],
                    defaults={"type_mouvement": data["type_mouvement"]},
                )

            admin_user = User.objects.create_user(
                username=options["admin_username"],
                email=options["admin_email"],
                password=password,
                first_name=options["admin_first_name"],
                last_name=options["admin_last_name"],
            )
            membre = Membre.objects.create(
                user=admin_user, chorale=chorale,
                numero_membre=Membre.generer_numero(chorale),
                date_adhesion=timezone.now().date(),
                statut=Membre.Statut.ACTIF,
            )
            Mandat.objects.create(
                membre=membre, poste=postes["Président"],
                date_debut=timezone.now().date(), is_active=True,
            )

        self.stdout.write(self.style.SUCCESS(f"Chorale « {chorale.nom} » ({chorale.prefix}) provisionnée."))
        self.stdout.write(f"  Pupitres : {len(PUPITRES_STANDARDS)} · Postes : {len(POSTES_STANDARDS)} · Catégories financières : {len(CATEGORIES_MOUVEMENT_STANDARDS)}")
        self.stdout.write(self.style.SUCCESS(f"Compte Bureau (Président) : {admin_user.username}"))
        if mot_de_passe_genere:
            self.stdout.write(self.style.WARNING(
                f"Mot de passe généré (à transmettre puis faire changer) : {password}"
            ))
