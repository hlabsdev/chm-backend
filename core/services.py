"""
ChoirManager — Core Services
==============================
Logique de provisionnement d'une chorale, partagée entre :
- la commande `manage.py provision_chorale` (opérateur, ligne de commande) ;
- l'action d'administration « Approuver et provisionner » sur DemandeChorale
  (opérateur, modération d'une demande publique).

Centralisée ici pour ne jamais dupliquer le bootstrap (pupitres, postes,
catégories financières, premier compte Bureau) entre les deux points d'entrée.
"""

import secrets
import string

from django.contrib.auth.models import Group, User
from django.db import transaction
from django.utils import timezone

from finances.models import CategorieMouvement
from membres.models import Mandat, Membre, Poste, Pupitre

from .models import Chorale

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


class ProvisionnementError(Exception):
    """Levée si les données fournies ne permettent pas de provisionner (doublons…)."""


def generer_mot_de_passe() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(14))


@transaction.atomic
def provisionner_chorale(
    *, nom: str, prefix: str, admin_username: str, admin_email: str,
    admin_first_name: str, admin_last_name: str,
    currency: str = Chorale.Monnaie.XOF, admin_password: str | None = None,
    admin_sexe: str = "", admin_telephone: str = "",
) -> tuple[Chorale, User, str, bool]:
    """
    Crée une chorale immédiatement utilisable : pupitres/postes/catégories
    standards + premier compte Bureau (Président, mandat actif).

    `admin_sexe` et `admin_telephone` sont optionnels et laissés VIDES par
    défaut : sur une vraie chorale, ces données appartiennent à la personne et
    ne s'infèrent pas d'un prénom. Elles sont exposées en options de la
    commande pour pouvoir renseigner un profil complet dès le provisionnement
    plutôt que de laisser le premier compte Bureau incomplet — le sexe
    conditionne notamment les tarifs de cotisation par genre.

    Renvoie (chorale, admin_user, mot_de_passe, mot_de_passe_genere).
    Lève ProvisionnementError si nom/préfixe/identifiant sont déjà pris.
    """
    nom = nom.strip()
    prefix = prefix.strip().upper()

    if not nom:
        raise ProvisionnementError("Le nom de la chorale est requis.")
    if not prefix:
        raise ProvisionnementError("Le préfixe est requis.")
    if Chorale.objects.filter(nom__iexact=nom).exists():
        raise ProvisionnementError(f"Une chorale nommée « {nom} » existe déjà.")
    if Chorale.objects.filter(prefix__iexact=prefix).exists():
        raise ProvisionnementError(f"Le préfixe « {prefix} » est déjà utilisé par une autre chorale.")
    if User.objects.filter(username=admin_username).exists():
        raise ProvisionnementError(f"Le nom d'utilisateur « {admin_username} » est déjà pris.")

    password = admin_password or generer_mot_de_passe()
    mot_de_passe_genere = admin_password is None

    chorale = Chorale.objects.create(
        nom=nom, prefix=prefix, currency=currency, date_creation=timezone.now().date(),
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
        username=admin_username, email=admin_email, password=password,
        first_name=admin_first_name, last_name=admin_last_name,
    )
    membre = Membre.objects.create(
        user=admin_user, chorale=chorale,
        numero_membre=Membre.generer_numero(chorale),
        date_adhesion=timezone.now().date(),
        statut=Membre.Statut.ACTIF,
        sexe=admin_sexe,
        telephone=admin_telephone,
    )
    Mandat.objects.create(
        membre=membre, poste=postes["Président"],
        date_debut=timezone.now().date(), is_active=True,
    )

    return chorale, admin_user, password, mot_de_passe_genere
