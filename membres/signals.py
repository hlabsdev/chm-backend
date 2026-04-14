"""
ChoirManager — Signal de synchronisation RBAC
===============================================
Synchronise automatiquement les groupes Django d'un utilisateur
à chaque modification d'un Mandat.

Logique :
  1. Récupérer tous les groupes Django liés aux mandats ACTIFS du membre.
  2. Ajouter le groupe de base selon le statut du membre.
  3. Écraser user.groups avec ce résultat.

Cela garantit que les permissions reflètent toujours la réalité des mandats,
sans qu'aucune vue ou serializer n'ait à s'en préoccuper.
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


@receiver(post_save, sender=Mandat)
def sync_groupes_membre(sender, instance: Mandat, **kwargs) -> None:
    """
    Recalcule et applique les groupes Django du membre concerné
    à chaque modification d'un Mandat.

    Ce signal est le cœur du système RBAC : il fait le pont entre
    le modèle organisationnel (Postes/Mandats) et le système de
    permissions Django (Groupes).
    """
    membre = instance.membre
    user = membre.user

    # 1. Groupes issus des mandats actifs (via la M2M Poste.groupes)
    groupes_mandats = list(
        Group.objects.filter(
            postes__mandats__membre=membre,
            postes__mandats__is_active=True,
        ).distinct()
    )

    # 2. Groupe de base selon le statut du membre
    nom_base = _GROUPE_BASE_PAR_STATUT.get(membre.statut)
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
