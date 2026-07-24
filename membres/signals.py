"""
ChoirManager — Signaux de synchronisation RBAC
================================================
Synchronise automatiquement les groupes Django d'un utilisateur.

Logique de recalcul (synchroniser_groupes) :
  1. Récupérer tous les groupes Django liés aux mandats ACTIFS du membre.
  2. Ajouter le groupe de base selon le statut du membre.
  3. Écraser user.groups avec ce résultat.

Déclencheurs :
  - post_save sur Mandat  → attribution/clôture d'un poste ;
  - post_save sur Membre  → création (membre_actif dès le départ), changement
    de statut (actif → honoraire/inactif…), soft-delete/restore.

Sans le second déclencheur, un membre créé sans mandat n'obtenait jamais
`membre_actif`, un changement de statut ne retirait jamais l'ancien groupe
de base, et un soft-delete (qui clôture les mandats via .update(), donc sans
signal Mandat) laissait des permissions fantômes — un membre bureau supprimé
puis restauré retrouvait ses droits bureau sans mandat actif.

Cela garantit que les permissions reflètent toujours la réalité des mandats
et du statut, sans qu'aucune vue ou serializer n'ait à s'en préoccuper.
"""

from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Mandat, Membre


# Correspondance statut membre → groupe de base Django
_GROUPE_BASE_PAR_STATUT = {
    Membre.Statut.ACTIF:     "membre_actif",
    Membre.Statut.STAGIAIRE: "membre_actif",       # même accès que actif
    Membre.Statut.HONORAIRE: "membre_honoraire",
    Membre.Statut.INACTIF:   None,                 # aucun groupe de base
}


def synchroniser_groupes(membre: Membre) -> None:
    """
    Recalcule et applique les groupes Django du membre : groupes issus des
    mandats actifs + groupe de base selon le statut. Un membre soft-deleted
    ne conserve aucun groupe (ses mandats sont clôturés, son statut inactif).
    """
    user = membre.user

    # 1. Groupes issus des mandats actifs (via la M2M Poste.groupes)
    groupes_mandats = list(
        Group.objects.filter(
            postes__mandats__membre=membre,
            postes__mandats__is_active=True,
        ).distinct()
    )

    # 2. Groupe de base selon le statut du membre
    nom_base = None if membre.is_deleted else _GROUPE_BASE_PAR_STATUT.get(membre.statut)
    groupes_finaux = groupes_mandats[:]

    if nom_base:
        try:
            groupes_finaux.insert(0, Group.objects.get(name=nom_base))
        except Group.DoesNotExist:
            # Les groupes de base n'ont pas encore été créés (première migration).
            # Ne pas bloquer — ils seront ajoutés lors de la data migration.
            pass

    # 3. Appliquer (remplace tous les groupes existants)
    user.groups.set(groupes_finaux)


@receiver(post_save, sender=Mandat)
def sync_groupes_sur_mandat(sender, instance: Mandat, **kwargs) -> None:
    """Attribution ou clôture d'un poste → recalcul des groupes du membre."""
    synchroniser_groupes(instance.membre)


@receiver(post_save, sender=Membre)
def sync_groupes_sur_membre(sender, instance: Membre, **kwargs) -> None:
    """Création / changement de statut / soft-delete → recalcul des groupes."""
    synchroniser_groupes(instance)
