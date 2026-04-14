"""
ChoirManager — Membres Filters
================================
Filtres django-filter pour les ViewSets membres.
"""

import django_filters

from .models import Membre


class MembreFilter(django_filters.FilterSet):
    """
    Filtres disponibles sur l'endpoint /api/membres/ :
    - ?statut=actif
    - ?pupitre=1
    - ?date_adhesion_min=2024-01-01
    - ?date_adhesion_max=2024-12-31
    - ?search=dupont (via SearchFilter DRF, pas ici)
    """
    statut = django_filters.ChoiceFilter(choices=Membre.Statut.choices)
    pupitre = django_filters.NumberFilter(field_name="pupitre_id")
    date_adhesion_min = django_filters.DateFilter(
        field_name="date_adhesion", lookup_expr="gte"
    )
    date_adhesion_max = django_filters.DateFilter(
        field_name="date_adhesion", lookup_expr="lte"
    )

    class Meta:
        model = Membre
        fields = ["statut", "pupitre", "date_adhesion_min", "date_adhesion_max"]
