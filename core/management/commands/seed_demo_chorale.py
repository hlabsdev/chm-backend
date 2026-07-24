"""
ChoirManager — Seed d'une 2e chorale de démo (QA multi-tenant)
==================================================================
Réservé au dev/QA : peuple une seconde chorale complète (bureau, maître
de chœur, choristes répartis par pupitre) pour vérifier À LA MAIN que
l'isolation multi-tenant tient — deux sessions/navigateurs, deux
chorales, aucune fuite de données de l'une vers l'autre.

Reprend aussi le nom de 1-2 membres d'une chorale existante (comptes
Django distincts, car Membre.user est un OneToOneField — une personne
ne peut pas partager un login entre deux chorales) pour simuler le cas
« la même personne physique est membre des deux chorales ».

Affiche tous les identifiants générés en clair dans la console — ne
JAMAIS exécuter cette commande sur un environnement de production.
"""

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from core.models import Chorale
from membres.models import Mandat, Membre, Poste, Pupitre

DEMO_PASSWORD = "Demo1234!"

# (prénom, nom, pupitre, sexe) — le sexe est cohérent avec le prénom et n'est
# pas décoratif : les tarifs de cotisation peuvent être différenciés par genre
# (cf. finances.TarifCotisation). Un jeu de démo sans sexe renseigné laisse ce
# pan des finances non exerçable.
DEMO_MEMBRES = [
    ("Awa", "Traoré", "Soprano", Membre.Sexe.FEMME),
    ("Fatou", "Diallo", "Soprano", Membre.Sexe.FEMME),
    ("Moussa", "Koné", "Alto", Membre.Sexe.HOMME),
    ("Aïcha", "Bamba", "Alto", Membre.Sexe.FEMME),
    ("Ibrahim", "Sanogo", "Ténor", Membre.Sexe.HOMME),
    ("Salif", "Ouédraogo", "Ténor", Membre.Sexe.HOMME),
    ("Kader", "Cissé", "Basse", Membre.Sexe.HOMME),
    ("Youssouf", "Konaté", "Basse", Membre.Sexe.HOMME),
]


class Command(BaseCommand):
    help = "Seed une 2e chorale de démo (bureau + MDC + choristes) pour vérifier l'isolation multi-tenant. Dev/QA uniquement."

    def add_arguments(self, parser):
        parser.add_argument("--nom", default="Chorale Voix Nouvelles")
        parser.add_argument("--prefix", default="CVN")

    # Une seule transaction pour tout le seed : `Membre.generer_numero()` prend
    # un verrou sur la ligne Chorale et exige d'être appelée dans un bloc
    # atomique. Cela garantit aussi qu'un seed interrompu ne laisse pas une
    # chorale à moitié peuplée.
    @transaction.atomic
    def handle(self, *args, **options):
        nom = options["nom"]
        prefix = options["prefix"]

        if Chorale.objects.filter(nom__iexact=nom).exists():
            self.stdout.write(self.style.WARNING(f"« {nom} » existe déjà — rien à faire."))
            return

        call_command(
            "provision_chorale",
            nom=nom, prefix=prefix,
            admin_username=f"bureau_{prefix.lower()}",
            admin_email=f"bureau@{prefix.lower()}.demo",
            admin_first_name="Présidente",
            admin_last_name=nom,
            admin_password=DEMO_PASSWORD,
            admin_sexe=Membre.Sexe.FEMME,
            admin_telephone="+228 90 00 00 00",
            stdout=self.stdout,
        )
        chorale = Chorale.objects.get(nom=nom)
        pupitres = {p.nom: p for p in Pupitre.objects.filter(chorale=chorale)}
        credentials = [(f"bureau_{prefix.lower()}", "Présidente (Bureau)")]

        # Maître de chœur
        poste_mdc = Poste.objects.get(chorale=chorale, nom="Maître de chœur Principal")
        mdc_user = User.objects.create_user(
            username=f"mdc_{prefix.lower()}", email=f"mdc@{prefix.lower()}.demo",
            password=DEMO_PASSWORD, first_name="Chef", last_name="De Chœur",
        )
        mdc_membre = Membre.objects.create(
            user=mdc_user, chorale=chorale, numero_membre=Membre.generer_numero(chorale),
            date_adhesion=timezone.now().date(), statut=Membre.Statut.ACTIF,
            sexe=Membre.Sexe.HOMME, telephone="+228 90 00 00 01",
        )
        Mandat.objects.create(membre=mdc_membre, poste=poste_mdc, date_debut=timezone.now().date(), is_active=True)
        credentials.append((mdc_user.username, "Maître de chœur"))

        # Choristes répartis par pupitre
        for i, (prenom, nom_famille, pupitre_nom, sexe) in enumerate(DEMO_MEMBRES, start=1):
            username = f"{prefix.lower()}_membre{i}"
            user = User.objects.create_user(
                username=username, email=f"{username}@{prefix.lower()}.demo",
                password=DEMO_PASSWORD, first_name=prenom, last_name=nom_famille,
            )
            Membre.objects.create(
                user=user, chorale=chorale, numero_membre=Membre.generer_numero(chorale),
                date_adhesion=timezone.now().date(), statut=Membre.Statut.ACTIF,
                pupitre=pupitres.get(pupitre_nom),
                sexe=sexe, telephone=f"+228 90 00 01 {i:02d}",
            )
            credentials.append((username, f"Choriste — {pupitre_nom}"))

        # Scénario homonymie : même personne, deux tenants, deux comptes distincts.
        homonymes = []
        # On vise la chorale la PLUS peuplée, pas la première par id : la
        # migration de bootstrap crée une chorale vide qui arrive en tête, et
        # le scénario d'homonymie ne se déclenchait donc jamais (0 compte
        # produit, silencieusement).
        autre_chorale = (
            Chorale.objects.exclude(id=chorale.id)
            .annotate(nb=Count("membres"))
            .filter(nb__gt=0)
            .order_by("-nb", "id")
            .first()
        )
        if autre_chorale:
            for m in Membre.objects.filter(chorale=autre_chorale).select_related("user", "pupitre")[:2]:
                username = f"{prefix.lower()}_{m.user.username}"
                if User.objects.filter(username=username).exists():
                    continue
                user = User.objects.create_user(
                    username=username, email=f"{username}@{prefix.lower()}.demo",
                    password=DEMO_PASSWORD, first_name=m.user.first_name, last_name=m.user.last_name,
                )
                pupitre = pupitres.get(m.pupitre.nom) if m.pupitre_id else None
                Membre.objects.create(
                    user=user, chorale=chorale, numero_membre=Membre.generer_numero(chorale),
                    date_adhesion=timezone.now().date(), statut=Membre.Statut.ACTIF, pupitre=pupitre,
                    # Même personne physique dans les deux tenants : on reprend
                    # son profil réel plutôt que de laisser les champs vides.
                    sexe=m.sexe, telephone=m.telephone,
                )
                role = f"Choriste — homonyme de {m.user.get_full_name()} ({autre_chorale.nom})"
                credentials.append((username, role))
                homonymes.append(username)

        self.stdout.write(self.style.SUCCESS(f"\n« {chorale.nom} » ({chorale.prefix}) peuplée : {len(credentials)} comptes (mot de passe unique : {DEMO_PASSWORD}).\n"))
        largeur = max(len(u) for u, _ in credentials) + 2
        for username, role in credentials:
            self.stdout.write(f"  {username:<{largeur}}{role}")
        if homonymes:
            self.stdout.write(self.style.WARNING(
                "\nPour tester l'isolation : connecte-toi avec un de ces comptes homonymes "
                "et avec le compte de la chorale d'origine (même nom affiché, deux logins "
                "différents) — aucune donnée (présences, cotisations, répertoire) ne doit "
                "être visible de l'un vers l'autre."
            ))
