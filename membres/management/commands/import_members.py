import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify
from core.models import Chorale
from membres.models import Membre, Pupitre

class Command(BaseCommand):
    help = "Importe une liste de membres pour une chorale spécifique"

    def add_arguments(self, parser):
        parser.add_argument('--chorale', type=str, help="Nom de la chorale", default="REJOICE AND PRAISE THE LORD")

    def handle(self, *args, **options):
        nom_chorale = options['chorale']
        
        # 1. Récupérer ou créer la chorale de base
        chorale, _ = Chorale.objects.get_or_create(
            nom=nom_chorale,
            defaults={
                'prefix': 'RPL',
                'date_creation': datetime.date.today()
            }
        )

        members_data = [
            ("ABALOVI", "Kossiwa", "90764319", "Tenor"),
            ("AFETSE", "Afi Lawè", "96505503", "Soprano"),
            ("AMEWOU", "Ablavi cathérine", "98438001", "Soprano"),
            ("AMOUZOUVI", "Akona Monique", "91135054", "Alto"),
            ("APOUBI", "Kossi Elie", "91533855", "Basse"),
            ("BAKANA", "Adjovi Justine", "", "Alto"),
            ("DJODJI", "Reine Adjo Mawusé", "98225912", "Alto"),
            ("ESSOU", "Adjo Essénam", "98485200", "Soprano"),
            ("GOLO", "Kekeli Hermann", "91025263", "Soprano"),
            ("GUENOUKPATI", "Kossi Edem", "97725400", "Tenor"),
            ("KANGNI", "Akouvi Aurélie", "90970718", "Soprano"),
            ("KOFFI", "Afoi", "98918047", "Soprano"),
            ("KOWOU", "Adjovi Rachel", "91224379", "Soprano"),
            ("KOWOU", "Koami Edoh Ezékiel", "90306113", "Soprano"),
            ("KPETSE", "Atsou", "90720585", "Basse"),
            ("SIADONOU", "Ablavi Bénédicte", "79774428", "Soprano"),
            ("SOSSA", "Kodjo", "96889913", "Basse"),
            ("SUNU", "Elina Amélé", "99020281", "Alto"),
            ("SUNU", "Kodjo Joseph", "92566961", "Tenor"),
            ("TOMETSI", "Afi Dogbeda", "98132703", "Soprano"),
            ("TOSSOU", "Ayélé", "", "Soprano"),
            ("TOSSOU", "Kai", "", "Soprano"),
            ("TOSSOU", "Elaris", "99746314", "Soprano")
        ]

        self.stdout.write(f"Importation des membres pour : {chorale.nom}")

        with transaction.atomic():
            for nom, prenom, tel, pupitre_nom in members_data:
                # 2. Gérer le pupitre
                cat_slug = pupitre_nom.lower()
                pupitre, _ = Pupitre.objects.get_or_create(
                    chorale=chorale,
                    nom=pupitre_nom,
                    defaults={'categorie': cat_slug}
                )

                # 3. Créer le User Django (username unique basé sur nom/prenom)
                username = slugify(f"{prenom}.{nom}")
                if User.objects.filter(username=username).exists():
                    username = f"{username}.{tel[-4:]}" if tel else f"{username}.{id(nom)}"

                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'first_name': prenom,
                        'last_name': nom,
                        'is_active': True
                    }
                )
                
                if created:
                    user.set_password("Chorale2024!") # Mot de passe par défaut
                    user.save()

                # 4. Créer le Membre (si non existant)
                if not hasattr(user, 'membre'):
                    num_membre = Membre.generer_numero(chorale)
                    Membre.objects.create(
                        user=user,
                        chorale=chorale,
                        numero_membre=num_membre,
                        date_adhesion=datetime.date.today(),
                        telephone=tel,
                        pupitre=pupitre,
                        statut=Membre.Statut.ACTIF
                    )
                    self.stdout.write(self.style.SUCCESS(f"Créé: {prenom} {nom} ({num_membre})"))
                else:
                    self.stdout.write(self.style.WARNING(f"Saut d'étape: {prenom} {nom} (déjà membre)"))

        self.stdout.write(self.style.SUCCESS("Importation terminée avec succès !"))