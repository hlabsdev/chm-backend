"""
ChoirManager — Service de notification
==========================================
Point d'entrée UNIQUE pour notifier un ou plusieurs membres. Les vues
métier appellent `notifier(...)` / `notifier_groupe(...)` — jamais
Notification.objects.create directement — pour que la politique
(in-app + email ou in-app seul) reste centralisée ici.

Emails : best-effort (`fail_silently=True`). Une notification métier ne
doit JAMAIS faire échouer l'action qui la déclenche (approuver une
absence doit réussir même si le serveur SMTP est en panne). En dev,
EMAIL_BACKEND=console affiche les mails dans le terminal du runserver.

Cas couverts (voir les vues appelantes) :
- demande d'absence approuvée/refusée   → in-app + email (demandeur)
- poste attribué / mandat clôturé        → in-app (membre concerné)
- annonce publiée                        → in-app (tous les membres actifs)
- cotisations générées (campagne)        → in-app (membres concernés)
- demande d'adhésion chorale traitée     → email seul (le contact n'a pas
  encore de compte → pas de notification in-app possible)
"""

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification


def _envoyer_email(destinataire_email: str, sujet: str, corps: str) -> None:
    if not destinataire_email:
        return
    send_mail(
        subject=f"[ChoirManager] {sujet}",
        message=corps,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[destinataire_email],
        fail_silently=True,
    )


def notifier(
    membre,
    *,
    type_notification: str,
    titre: str,
    message: str = "",
    lien: str = "",
    par_email: bool = False,
) -> Notification:
    """Crée une notification in-app pour un membre (+ email optionnel)."""
    notif = Notification.objects.create(
        chorale=membre.chorale,
        destinataire=membre,
        type_notification=type_notification,
        titre=titre,
        message=message,
        lien=lien,
    )
    if par_email:
        _envoyer_email(membre.email, titre, message or titre)
    return notif


def notifier_groupe(
    membres,
    *,
    type_notification: str,
    titre: str,
    message: str = "",
    lien: str = "",
) -> int:
    """
    Notification in-app en masse (jamais d'email en masse — une annonce
    ne doit pas transformer la plateforme en canon à spam SMTP).
    Renvoie le nombre de notifications créées.
    """
    notifs = [
        Notification(
            chorale=membre.chorale,
            destinataire=membre,
            type_notification=type_notification,
            titre=titre,
            message=message,
            lien=lien,
        )
        for membre in membres
    ]
    Notification.objects.bulk_create(notifs)
    return len(notifs)


def envoyer_email_externe(email: str, sujet: str, corps: str) -> None:
    """
    Email vers une personne SANS compte membre (ex. contact d'une demande
    d'adhésion chorale). Best-effort, comme le reste.
    """
    _envoyer_email(email, sujet, corps)
