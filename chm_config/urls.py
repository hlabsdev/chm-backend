"""
ChoirManager — URL Configuration
==================================
Routage API principal. Toutes les routes sont préfixées par /api/.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Administration Django
    path("admin/", admin.site.urls),

    # API v1
    path("api/core/", include("core.urls")),
    path("api/auth/", include("authentication.urls")),
    path("api/membres/", include("membres.urls")),
    path("api/musique/", include("musique.urls")),
    path("api/presences/", include("presences.urls")),
    path("api/finances/", include("finances.urls")),
]

# Servir les fichiers media en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
