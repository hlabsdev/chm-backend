"""
ChoirManager — Data Migration Bootstrap
==========================================
Crée les données initiales :
- Groupes Django pour le RBAC
- Une chorale de démonstration
- Pupitres standards
- Postes standards avec groupes associés
- Catégories de mouvements financières
"""

from django.db import migrations


def create_bootstrap_data(apps, schema_editor):
    """Création des données initiales pour le fonctionnement du RBAC."""
    Group = apps.get_model("auth", "Group")
    Chorale = apps.get_model("core", "Chorale")
    Pupitre = apps.get_model("membres", "Pupitre")
    Poste = apps.get_model("membres", "Poste")
    CategorieMouvement = apps.get_model("finances", "CategorieMouvement")

    # -----------------------------------------------------------------------
    # 1. Groupes Django (base du système RBAC)
    # -----------------------------------------------------------------------
    groupes = {}
    for nom in [
        "membre_actif", "membre_honoraire",
        "bureau", "tresorier", "maitre_choeur", "chef_pupitre",
    ]:
        groupes[nom], _ = Group.objects.get_or_create(name=nom)

    # -----------------------------------------------------------------------
    # 2. Chorale de démonstration
    # -----------------------------------------------------------------------
    chorale, _ = Chorale.objects.get_or_create(
        nom="Ma Chorale",
        defaults={
            "prefix": "MCH",
            "description": "Chorale de démonstration — modifiez ces informations dans l'admin.",
            "date_creation": "2024-01-01",
        },
    )

    # -----------------------------------------------------------------------
    # 3. Pupitres standards
    # -----------------------------------------------------------------------
    pupitres_data = [
        {"nom": "Soprano", "categorie": "soprano", "ordre": 1},
        {"nom": "Alto", "categorie": "alto", "ordre": 2},
        {"nom": "Ténor", "categorie": "tenor", "ordre": 3},
        {"nom": "Basse", "categorie": "basse", "ordre": 4},
    ]
    for data in pupitres_data:
        Pupitre.objects.get_or_create(
            chorale=chorale, nom=data["nom"],
            defaults={"categorie": data["categorie"], "ordre": data["ordre"]},
        )

    # -----------------------------------------------------------------------
    # 4. Postes standards avec groupes associés
    # -----------------------------------------------------------------------
    postes_data = [
        {
            "nom": "Président",
            "type_poste": "bureau",
            "unique_actif": True,
            "groupes": ["bureau"],
        },
        {
            "nom": "Vice-Président",
            "type_poste": "bureau",
            "unique_actif": True,
            "groupes": ["bureau"],
        },
        {
            "nom": "Secrétaire Général",
            "type_poste": "bureau",
            "unique_actif": True,
            "groupes": ["bureau"],
        },
        {
            "nom": "Trésorier",
            "type_poste": "bureau",
            "unique_actif": True,
            "groupes": ["bureau", "tresorier"],
        },
        {
            "nom": "Commissaire aux comptes",
            "type_poste": "bureau",
            "unique_actif": True,
            "groupes": ["bureau"],
        },
        {
            "nom": "Maître de chœur Principal",
            "type_poste": "direction",
            "unique_actif": True,
            "groupes": ["maitre_choeur"],
        },
        {
            "nom": "Maître de chœur Suppléant",
            "type_poste": "direction",
            "unique_actif": False,  # Plusieurs suppléants possibles
            "groupes": ["maitre_choeur"],
        },
        {
            "nom": "Chef de pupitre",
            "type_poste": "technique",
            "unique_actif": False,  # Un par pupitre
            "groupes": ["chef_pupitre"],
        },
    ]

    for data in postes_data:
        poste, created = Poste.objects.get_or_create(
            chorale=chorale,
            nom=data["nom"],
            defaults={
                "type_poste": data["type_poste"],
                "unique_actif": data["unique_actif"],
            },
        )
        if created:
            for nom_groupe in data["groupes"]:
                poste.groupes.add(groupes[nom_groupe])

    # -----------------------------------------------------------------------
    # 5. Catégories de mouvements financiers
    # -----------------------------------------------------------------------
    categories_data = [
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
    for data in categories_data:
        CategorieMouvement.objects.get_or_create(
            chorale=chorale,
            nom=data["nom"],
            defaults={"type_mouvement": data["type_mouvement"]},
        )


def reverse_bootstrap(apps, schema_editor):
    """Rollback : ne supprime rien pour éviter les pertes de données."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0001_initial"),
        ("membres", "0001_initial"),
        ("finances", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_bootstrap_data, reverse_bootstrap),
    ]
