"""
ChoirManager — Rapports URLs
==============================
Routes : /api/rapports/
"""

from django.urls import path

from . import views

app_name = "rapports"

urlpatterns = [
    path("financier/", views.RapportFinancierView.as_view(), name="financier"),
    path("presences/", views.RapportPresencesView.as_view(), name="presences"),
    path("effectifs/", views.RapportEffectifsView.as_view(), name="effectifs"),
    path("repertoire/", views.RapportRepertoireView.as_view(), name="repertoire"),
]
