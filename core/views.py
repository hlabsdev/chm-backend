from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
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
            return Response({"detail": "Chorale non trouvée."}, status=400)

        is_staff = request.user.is_superuser or request.user.groups.filter(name__in=["bureau", "maitre_choeur"]).exists()

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
                    "titre": dernier_chant.titre,
                    "created_at": dernier_chant.created_at
                }

            return Response({
                "role": "choriste",
                "chants_count": chants_count,
                "prochaine_repetition": rep_data,
                "cotisation_status": "À jour", # Mock for now
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
            "taux_presence": 85, # Mock
            "prochaine_repetition": rep_data,
            "demandes_absence": demandes_data,
            "pupitres": pupitres_stats,
            "programme": [] # Mock
        })
