"""
Filtres de gabarit pour les rapports PDF.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

# Espace insécable : évite un retour à la ligne au milieu d'un montant.
_INSECABLE = " "


@register.filter
def montant(valeur):
    """
    Formate un montant avec séparateur de milliers (convention francophone :
    114 000). Sans décimales si entier, sinon 2. L'espace est insécable.
    """
    try:
        d = Decimal(str(valeur))
    except (InvalidOperation, ValueError, TypeError):
        return valeur
    entier = d == d.to_integral_value()
    brut = f"{d:,.0f}" if entier else f"{d:,.2f}"
    return brut.replace(",", _INSECABLE).replace(".", ",")
