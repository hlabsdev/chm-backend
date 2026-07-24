from django.urls import path
from .views import DashboardStatsView, DemandeChoraleCreateView, HealthView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('demandes-chorale/', DemandeChoraleCreateView.as_view(), name='demande-chorale-create'),
]
