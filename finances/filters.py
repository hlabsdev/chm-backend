"""
ChoirManager — Finances Filters
=================================
Filtres django-filter pour le journal de caisse.
"""

import django_filters

from .models import Mouvement


class MouvementFilter(django_filters.FilterSet):
    """
    Filtres sur /api/finances/mouvements/ :
    - ?sens=entree|sortie
    - ?categorie=1
    - ?membre=5
    - ?date_min=2026-01-01 & ?date_max=2026-12-31
    """
    date_min = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_max = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = Mouvement
        fields = ["sens", "categorie", "membre", "date_min", "date_max"]
