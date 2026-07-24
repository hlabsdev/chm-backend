from django.urls import path
from .views import DashboardStatsView, DemandeChoraleCreateView

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('demandes-chorale/', DemandeChoraleCreateView.as_view(), name='demande-chorale-create'),
]
