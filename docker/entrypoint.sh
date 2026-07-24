#!/bin/sh
# ============================================================================
# ChoirManager — Entrypoint backend
# ============================================================================
# Préparation minimale, volontairement passive.
#
# Ce script n'applique JAMAIS les migrations : elles sont jouées une seule fois
# par le service Compose `migrate`, dont le backend dépend via
# `condition: service_completed_successfully`. Les exécuter ici les relancerait
# dans chaque worker Gunicorn, en concurrence les uns avec les autres.
#
# Il n'importe rien non plus depuis une ancienne base SQLite : un conteneur doit
# pouvoir démarrer sur une base PostgreSQL vide.
#
# Sans argument  -> démarre Gunicorn (service applicatif).
# Avec arguments -> les exécute tels quels, ce qui permet
#                   `docker compose run --rm backend python manage.py ...`.

set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Le nombre de workers n'est pas figé dans l'image : il dépend de la mémoire et
# du CPU de la cible et doit être mesuré, pas recopié.
exec gunicorn chm_config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile -
