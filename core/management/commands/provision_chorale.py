"""
ChoirManager — Provisionnement d'une nouvelle chorale (ligne de commande)
=============================================================================
Voie officielle #1 pour qu'une nouvelle chorale rejoigne la plateforme,
à l'initiative directe de l'opérateur (sans passer par une demande publique).
La voie #2 est la modération d'une DemandeChorale publique (cf. core/admin.py) ;
les deux appellent `core.services.provisionner_chorale` pour ne jamais
dupliquer le bootstrap (pupitres, postes, catégories, premier compte Bureau).
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import Chorale
from core.services import (
    CATEGORIES_MOUVEMENT_STANDARDS,
    POSTES_STANDARDS,
    PUPITRES_STANDARDS,
    ProvisionnementError,
    provisionner_chorale,
)
from membres.models import Membre


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
        # Profil du premier membre : optionnel, jamais deviné. Le sexe
        # conditionne les tarifs de cotisation par genre — le laisser vide
        # rend ce pan des finances inexploitable pour ce membre.
        parser.add_argument(
            "--admin-sexe", default="",
            choices=[""] + [s[0] for s in Membre.Sexe.choices],
            help="Sexe du premier compte Bureau (optionnel ; sert aux tarifs de cotisation par genre).",
        )
        parser.add_argument(
            "--admin-telephone", default="",
            help="Téléphone du premier compte Bureau (optionnel).",
        )

    def handle(self, *args, **options):
        try:
            chorale, admin_user, password, mot_de_passe_genere = provisionner_chorale(
                nom=options["nom"], prefix=options["prefix"], currency=options["currency"],
                admin_username=options["admin_username"], admin_email=options["admin_email"],
                admin_first_name=options["admin_first_name"], admin_last_name=options["admin_last_name"],
                admin_password=options["admin_password"],
                admin_sexe=options["admin_sexe"], admin_telephone=options["admin_telephone"],
            )
        except ProvisionnementError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Chorale « {chorale.nom} » ({chorale.prefix}) provisionnée."))
        self.stdout.write(
            f"  Pupitres : {len(PUPITRES_STANDARDS)} · Postes : {len(POSTES_STANDARDS)} · "
            f"Catégories financières : {len(CATEGORIES_MOUVEMENT_STANDARDS)}"
        )
        self.stdout.write(self.style.SUCCESS(f"Compte Bureau (Président) : {admin_user.username}"))
        if mot_de_passe_genere:
            self.stdout.write(self.style.WARNING(
                f"Mot de passe généré (à transmettre puis faire changer) : {password}"
            ))
