from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from core.permissions import IsBureauOrMaitreChoeur
from membres.models import Membre, Pupitre
from musique.models import Chant
from presences.models import Repetition, PermissionRequest
from django.utils import timezone
from django.db.models import Count

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        chorale = getattr(request, 'chorale', None)
        if not chorale:
            # Deux cas distincts derrière un request.chorale absent :
            if request.user.is_superuser:
                # Superuser : volontairement rattaché à aucune chorale
                # (cf. ChoraleMiddleware). Dashboard neutre, pas une erreur.
                return Response({
                    "role": "staff",
                    "detail": "Compte super-administrateur — non rattaché à une chorale.",
                    "membres_actifs": 0,
                    "chants_actifs": 0,
                    "taux_presence": 0,
                    "prochaine_repetition": None,
                    "demandes_absence": [],
                    "pupitres": [],
                    "programme": [],
                })

            # Utilisateur authentifié sans profil Membre : anomalie de données.
            # On la rend visible plutôt que de la masquer.
            return Response(
                {"detail": "Aucun profil membre n'est associé à ce compte. "
                           "Contactez un administrateur."},
                status=status.HTTP_403_FORBIDDEN,
            )

        is_staff = request.user.is_superuser or request.user.groups.filter(
            name__in=["bureau", "maitre_choeur", "tresorier"]
        ).exists()

        now = timezone.now()
        prochaine_rep = Repetition.objects.filter(chorale=chorale, date__gte=now.date()).order_by('date', 'heure_debut').first()

        if not is_staff:
            # Vue Choriste
            chants_count = Chant.objects.filter(chorale=chorale).count()
            rep_data = None
            if prochaine_rep:
                rep_data = {
                    "date": prochaine_rep.date,
                    "heure": prochaine_rep.heure_debut,
                    "lieu": prochaine_rep.lieu
                }

            dernier_chant = Chant.objects.filter(chorale=chorale).order_by('-created_at').first()
            dernier_chant_data = None
            if dernier_chant:
                dernier_chant_data = {
                    "id": dernier_chant.id,
                    "titre": dernier_chant.titre,
                    "created_at": dernier_chant.created_at
                }

            # Statut de cotisation réel : la cotisation la plus récente du
            # membre, non exonérée. « À jour » seulement si soldée.
            membre = getattr(request.user, "membre", None)
            cotisation_status = "Aucune cotisation"
            if membre is not None:
                from finances.models import Cotisation
                derniere = (
                    Cotisation.objects
                    .filter(membre=membre, is_deleted=False)
                    .exclude(statut=Cotisation.StatutCotisation.EXONERE)
                    .order_by("-created_at")
                    .first()
                )
                if derniere is not None:
                    cotisation_status = (
                        "À jour" if derniere.montant_paye >= derniere.montant_du
                        else "Impayée" if derniere.montant_paye == 0
                        else "Partielle"
                    )

            return Response({
                "role": "choriste",
                "chants_count": chants_count,
                "prochaine_repetition": rep_data,
                "cotisation_status": cotisation_status,
                "dernier_chant": dernier_chant_data
            })
        
        # Vue Staff
        membres_actifs = Membre.objects.filter(chorale=chorale, statut=Membre.Statut.ACTIF).count()
        chants_actifs = Chant.objects.filter(chorale=chorale).count()

        rep_data = None
        if prochaine_rep:
            rep_data = {
                "date": prochaine_rep.date,
                "heure": prochaine_rep.heure_debut,
                "lieu": prochaine_rep.lieu
            }

        # Taux de présence moyen sur les 4 dernières répétitions pointées (réel).
        dernieres_reps = Repetition.objects.filter(chorale=chorale).order_by("-date")[:4]
        taux_list = [r.taux_presence for r in dernieres_reps if r.taux_presence is not None]
        taux_moyen = round(sum(taux_list) / len(taux_list), 1) if taux_list else 0

        # Programme : chants travaillés à la prochaine séance (ou à la dernière).
        from musique.models import SeanceChant  # noqa: F401 (évite un import circulaire au chargement)
        rep_programme = prochaine_rep or dernieres_reps[0] if dernieres_reps else prochaine_rep
        programme = []
        if rep_programme:
            programme = [
                {"titre": sc.chant.titre, "statut": sc.statut}
                for sc in rep_programme.chants_travailles.select_related("chant")
            ]

        # Solde de caisse : visible uniquement bureau / trésorier / admin.
        is_finance = request.user.is_superuser or request.user.groups.filter(
            name__in=["bureau", "tresorier"]
        ).exists()
        solde = None
        if is_finance:
            from django.db.models import Sum as _Sum
            from finances.models import Mouvement
            mvts = Mouvement.objects.filter(chorale=chorale, is_deleted=False)
            entrees = mvts.filter(sens="entree").aggregate(t=_Sum("montant"))["t"] or 0
            sorties = mvts.filter(sens="sortie").aggregate(t=_Sum("montant"))["t"] or 0
            solde = entrees - sorties
        
        # Demandes d'absence
        demandes = PermissionRequest.objects.filter(
            chorale=chorale, 
            statut=PermissionRequest.StatutDemande.EN_ATTENTE
        ).select_related('membre__user')[:5]

        demandes_data = [
            {
                "id": d.id,
                "nom": d.membre.nom_complet,
                "initiales": f"{d.membre.user.first_name[0] if d.membre.user.first_name else ''}{d.membre.user.last_name[0] if d.membre.user.last_name else ''}".upper() or "M",
                "motif": d.motif
            } for d in demandes
        ]

        # Pupitres Stats
        pupitres_stats = []
        pupitres = Pupitre.objects.filter(chorale=chorale)
        total_membres = membres_actifs or 1
        for p in pupitres:
            count = p.membres.filter(statut=Membre.Statut.ACTIF).count()
            pupitres_stats.append({
                "nom": p.nom,
                "count": count,
                "pct": int((count / total_membres) * 100),
                "couleur": "#3b82f6" if p.categorie == 'tenor' else "#ef4444" if p.categorie == 'soprano' else "#f59e0b" if p.categorie == 'alto' else "#22c55e"
            })

        return Response({
            "role": "staff",
            "membres_actifs": membres_actifs,
            "chants_actifs": chants_actifs,
            "taux_presence": taux_moyen,
            "prochaine_repetition": rep_data,
            "demandes_absence": demandes_data,
            "pupitres": pupitres_stats,
            "programme": programme,
            "solde": solde,
        })
