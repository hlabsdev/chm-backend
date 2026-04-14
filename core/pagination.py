"""
ChoirManager — Pagination
==========================
Configuration de la pagination standard pour l'API.
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Pagination standard pour toutes les listes API.

    Paramètres query string :
    - page        : numéro de page (défaut 1)
    - page_size   : nombre d'éléments par page (défaut 25, max 100)
    """
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
