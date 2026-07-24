"""
ChoirManager — Retrait de la chorale de démonstration du bootstrap
===================================================================
La migration `0002_data_bootstrap` créait, en plus des groupes Django du RBAC,
une chorale « Ma Chorale » (MCH) avec ses pupitres, postes et catégories
financières. Elle a servi de bac à sable avant l'existence de
`provision_chorale`, qui crée désormais ces mêmes éléments proprement pour
chaque chorale réelle.

Cette chorale fantôme n'apporte plus rien et nuit : elle apparaît dans les
écrans d'administration, fausse les décomptes globaux, et le seeder de démo la
choisissait comme « autre chorale » pour son scénario d'homonymie (elle arrive
en tête par id, mais est vide), si bien que ce scénario ne produisait rien.

Les GROUPES Django créés par 0002 ne sont pas touchés : ils sont globaux et
restent la base du RBAC.

Prudence : la suppression n'a lieu que si la chorale est intacte — aucun
membre, et toujours son préfixe d'origine. Si quelqu'un l'a adoptée comme
chorale réelle, on n'y touche pas. `0002_data_bootstrap` n'est pas modifiée :
on ne réécrit pas une migration déjà appliquée.
"""

from django.db import migrations


def retirer_chorale_demo(apps, schema_editor):
    Chorale = apps.get_model("core", "Chorale")
    Membre = apps.get_model("membres", "Membre")

    chorale = Chorale.objects.filter(nom="Ma Chorale", prefix="MCH").first()
    if chorale is None:
        return

    if Membre.objects.filter(chorale=chorale).exists():
        # Elle a été adoptée pour un usage réel : on la laisse en place.
        return

    # Pupitres, postes et catégories financières partent en cascade via leur FK
    # chorale ; les groupes Django, eux, ne sont liés aux postes que par un M2M
    # et survivent donc.
    chorale.delete()


def reverse_noop(apps, schema_editor):
    """
    Pas de restauration : recréer une chorale de démonstration vide sur un
    rollback réintroduirait exactement le problème que cette migration corrige.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("membres", "0004_invitationchorale_membre_invitation_utilisee"),
        ("core", "0003_demandechorale"),
        ("finances", "0003_tarifcotisation"),
    ]

    operations = [
        migrations.RunPython(retirer_chorale_demo, reverse_noop),
    ]
