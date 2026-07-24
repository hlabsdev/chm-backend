import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify
from core.models import Chorale
from membres.models import Membre, Pupitre

# Libellés de la liste ci-dessous → libellés standards posés par
# `provision_chorale`. Le `categorie` doit rester le slug attendu par le modèle.
PUPITRES_ALIAS = {
    "Tenor": "Ténor",
    "Tenore": "Ténor",
    "Basse": "Basse",
    "Soprano": "Soprano",
    "Alto": "Alto",
}
PUPITRE_CATEGORIES = {
    "Soprano": "soprano",
    "Alto": "alto",
    "Ténor": "tenor",
    "Basse": "basse",
}


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

        # (nom, prénom, téléphone, pupitre, sexe)
        #
        # Le sexe alimente les tarifs de cotisation différenciés par genre
        # (finances.TarifCotisation) : le laisser vide rend ce pan des finances
        # inexploitable pour le membre.
        #
        # Il est ici DÉDUIT du prénom (jours de naissance éwé/mina : Kossi/Kodjo/
        # Koami masculins, Kossiwa/Adjo/Ablavi/Afi/Akouvi féminins) et des
        # prénoms français associés. Les prénoms non concluants restent VIDES
        # plutôt que devinés — il s'agit de personnes réelles. Le Bureau
        # complète depuis l'écran Membres.
        H, F, INCONNU = Membre.Sexe.HOMME, Membre.Sexe.FEMME, ""
        members_data = [
            ("ABALOVI", "Kossiwa", "90764319", "Tenor", F),
            ("AFETSE", "Afi Lawè", "96505503", "Soprano", F),
            ("AMEWOU", "Ablavi cathérine", "98438001", "Soprano", F),
            ("AMOUZOUVI", "Akona Monique", "91135054", "Alto", F),
            ("APOUBI", "Kossi Elie", "91533855", "Basse", H),
            ("BAKANA", "Adjovi Justine", "", "Alto", F),
            ("DJODJI", "Reine Adjo Mawusé", "98225912", "Alto", F),
            ("ESSOU", "Adjo Essénam", "98485200", "Soprano", F),
            ("GOLO", "Kekeli Hermann", "91025263", "Soprano", H),
            ("GUENOUKPATI", "Kossi Edem", "97725400", "Tenor", H),
            ("KANGNI", "Akouvi Aurélie", "90970718", "Soprano", F),
            ("KOFFI", "Afoi", "98918047", "Soprano", INCONNU),
            ("KOWOU", "Adjovi Rachel", "91224379", "Soprano", F),
            ("KOWOU", "Koami Edoh Ezékiel", "90306113", "Soprano", H),
            ("KPETSE", "Atsou", "90720585", "Basse", H),
            ("SIADONOU", "Ablavi Bénédicte", "79774428", "Soprano", F),
            ("SOSSA", "Kodjo", "96889913", "Basse", H),
            ("SUNU", "Elina Amélé", "99020281", "Alto", F),
            ("SUNU", "Kodjo Joseph", "92566961", "Tenor", H),
            ("TOMETSI", "Afi Dogbeda", "98132703", "Soprano", F),
            ("TOSSOU", "Ayélé", "", "Soprano", F),
            ("TOSSOU", "Kai", "", "Soprano", INCONNU),
            ("TOSSOU", "Elaris", "99746314", "Soprano", INCONNU),
        ]

        self.stdout.write(f"Importation des membres pour : {chorale.nom}")

        with transaction.atomic():
            for nom, prenom, tel, pupitre_nom, sexe in members_data:
                # 2. Gérer le pupitre
                # Les libellés de cette liste sont normalisés vers ceux que
                # `provision_chorale` a déjà créés (PUPITRES_STANDARDS) : sans
                # cela, « Tenor » créait un cinquième pupitre en double de
                # « Ténor », et les effectifs par pupitre se retrouvaient
                # scindés entre deux entrées.
                pupitre_nom = PUPITRES_ALIAS.get(pupitre_nom, pupitre_nom)
                pupitre, _ = Pupitre.objects.get_or_create(
                    chorale=chorale,
                    nom=pupitre_nom,
                    defaults={'categorie': PUPITRE_CATEGORIES.get(pupitre_nom, pupitre_nom.lower())}
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
                        statut=Membre.Statut.ACTIF,
                        sexe=sexe,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Créé: {prenom} {nom} ({num_membre})"))
                else:
                    self.stdout.write(self.style.WARNING(f"Saut d'étape: {prenom} {nom} (déjà membre)"))

        self.stdout.write(self.style.SUCCESS("Importation terminée avec succès !"))