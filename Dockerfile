# syntax=docker/dockerfile:1

# ============================================================================
# ChoirManager — Backend (Django 5 + DRF)
# ============================================================================
# Image multi-stage : les outils de compilation restent dans l'étage `builder`,
# l'image finale n'embarque que le venv construit et les libs de rendu PDF.

# --- Étape 1 : dépendances Python -------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libffi-dev \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


# --- Étape 2 : image d'exécution --------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# WeasyPrint charge Pango/Cairo/GDK-Pixbuf au runtime via ctypes : sans ces
# bibliothèques l'export PDF se dégrade proprement en 503 (cf. app `rapports`)
# alors que l'export CSV continue de fonctionner. On les installe donc ici pour
# que les deux exports marchent réellement dans l'image (critère §13).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      libpangoft2-1.0-0 \
      libgdk-pixbuf-2.0-0 \
      libcairo2 \
      libffi8 \
      shared-mime-info \
      fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv

# Utilisateur applicatif non privilégié (UID fixe : facilite les permissions
# sur un volume média monté depuis l'hôte).
RUN useradd --system --create-home --uid 10001 chm

WORKDIR /app
COPY --chown=chm:chm . .

# `/app` lui-même appartient à root (créé par WORKDIR) alors que son contenu est
# déjà copié en chm : pytest ne pouvait donc pas y créer son cache. On aligne le
# propriétaire du répertoire sur celui des fichiers qu'il contient.
RUN chmod +x /app/docker/entrypoint.sh \
 && mkdir -p /app/staticfiles /app/media \
 && chown chm:chm /app \
 && chown -R chm:chm /app/staticfiles /app/media

# Statiques collectés à la construction : l'exécution n'a alors plus besoin
# d'écrire dans l'image. Les variables ci-dessous ne servent QUE le temps de
# cette commande — collectstatic ne touche pas la base. Elles sont nécessaires
# parce que la configuration refuse désormais tout défaut permissif hors DEBUG.
RUN DJANGO_DEBUG=False \
    DJANGO_SECRET_KEY=build-time-only-never-used-at-runtime \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgresql://build:build@127.0.0.1:5432/build \
    python manage.py collectstatic --noinput --clear

USER chm
EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
