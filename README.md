# ChoirManager — Backend (API Django REST)

API multi-tenant de gestion de chorales (« chorales ») : membres, répertoire,
présences, finances, annonces et rapports. Django 5 + Django REST Framework,
authentification JWT, SQLite au stade MVP.

> Code en anglais (variables, classes, champs DB) ; textes UI, logs et
> commentaires métier en français — c'est volontaire et cohérent, ne pas
> « corriger ».

## Démarrage rapide

```bash
# depuis chm-backend/
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash ; ou venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate            # applique les migrations + le bootstrap RBAC
python manage.py createsuperuser    # compte admin plateforme (optionnel)
python manage.py runserver          # http://localhost:8000
```

Variables d'environnement (valeurs de dev par défaut, cf. `chm_config/settings.py`) :
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOW_ALL_ORIGINS`,
`WEASYPRINT_DLL_DIR` (voir Rapports/PDF), et `EMAIL_BACKEND` + `EMAIL_HOST*` +
`DEFAULT_FROM_EMAIL` (notifications par email en prod ; console en dev).

## Onboarding

### D'une nouvelle chorale — deux voies, jamais automatiques

**Voie opérateur (ligne de commande)** — crée la chorale + ses pupitres/postes/
catégories standards + le premier compte Bureau :

```bash
python manage.py provision_chorale \
  --nom "Ma Chorale" --prefix MCH \
  --admin-username president_mch --admin-email president@mch.example \
  --admin-first-name Awa --admin-last-name Traore
# mot de passe généré et affiché une seule fois si --admin-password est omis
```

**Voie demande publique + modération** — un formulaire public
(`POST /api/core/demandes-chorale/`, aussi exposé côté front sur
`/auth/demande-chorale`) crée une `DemandeChorale` `en_attente`. **Aucune
chorale n'est jamais créée automatiquement** : anti-abus par throttle IP
(5/jour), honeypot, et rejet des doublons email/nom en attente. L'opérateur
modère ensuite dans le Django admin (`/admin/core/demandechorale/`) : renseigne
le préfixe attribué puis lance l'action « Approuver et provisionner » (ou
« Rejeter »). Les deux voies partagent la même logique de bootstrap via
`core/services.py::provisionner_chorale` — ne jamais la dupliquer.

Pour peupler une **2e chorale de démo** (dev/QA multi-tenant : bureau, maître de
chœur, choristes par pupitre, comptes homonymes) :

```bash
python manage.py seed_demo_chorale        # ne jamais exécuter en production
```

### D'un choriste — invitation par code, jamais d'inscription libre

Il n'existe **volontairement pas** d'auto-inscription ouverte à qui devine une
URL (l'ancien endpoint de ce type, scopé par un `chorale_id` séquentiel
devinable, a été retiré). Un membre du Bureau génère un code d'invitation
(`POST /api/membres/invitations/`, section « Invitations » de l'écran Membres
côté front) : 8 caractères aléatoires, optionnellement limité en usages
(`max_utilisations`, 1 = invitation nominative) et/ou dans le temps
(`expire_le`). Le lien `/rejoindre/<code>` (public) vérifie le code
(`GET /api/membres/invitations/verifier/`, throttle 20/h) puis inscrit le
choriste dans **la** chorale du code (`POST /api/membres/invitations/rejoindre/`,
throttle 10/h, verrouillage `select_for_update` contre les usages concurrents
d'un code à quota limité) et le connecte immédiatement (JWT).

## Architecture

### Multi-tenant par `Chorale` (pas de DB séparée)

Chaîne de modèles abstraits dans `core/models.py` :

```
TimeStampedModel                        created_at / updated_at
  Chorale                               entité tenant racine (prefix, devise, logo…)
  ChoraleOwnedModel(TimeStampedModel)   ajoute FK `chorale`
    SoftDeleteModel(ChoraleOwnedModel)  ajoute is_deleted / soft_delete() / restore()
```

Isolation appliquée sur **deux couches à garder synchronisées** pour tout nouveau
modèle/viewset :
- `core/middleware.py` (`ChoraleMiddleware`) pose `request.chorale` (SimpleLazyObject)
  d'après le membre connecté (superuser → `None` = non filtré).
- `core/mixins.py` (`ChoraleFilterMixin`) sur chaque ViewSet filtre le queryset et
  injecte `chorale` à la création. `SoftDeleteMixin` transforme `DELETE` en
  `soft_delete()` et exclut les supprimés (sauf `?include_deleted=true`, superuser).

### RBAC via `Mandat` → `Poste` → Groupes Django

Les permissions ne sont jamais assignées directement. Un `Membre` porte des
`Mandat`s vers des `Poste`s (M2M vers des `Group` Django) ; le signal
`membres/signals.py` recalcule `user.groups` à chaque sauvegarde de mandat
(groupes des mandats actifs + groupe de base selon le statut). Les classes de
permission (`core/permissions.py` : `IsBureau`, `IsTresorier`,
`IsBureauOrMaitreChoeur`…) s'appuient sur ces groupes. Accorder/tester une
permission = créer/activer un `Mandat`, pas éditer `user.groups`.

### Apps

`core`, `authentication`, `membres`, `musique`, `presences`, `finances`,
`communications` (annonces), `rapports` (agrégation + exports), `notifications`
(in-app + email). Chaque app expose ses routes sous `/api/<app>/` (cf.
`chm_config/urls.py`). La logique métier vit dans `services.py` / `signals.py`,
pas dans les vues ou serializers.

### Notifications (in-app + email)

`notifications/services.py` est le **point d'entrée unique** — les vues appellent
`notifier()` / `notifier_groupe()` / `envoyer_email_externe()`, jamais
`Notification.objects.create` directement. Les emails sont **best-effort**
(`fail_silently=True`) : une notification ne doit jamais faire échouer l'action
métier qui la déclenche. Cas câblés : absence approuvée/refusée (in-app + email),
poste attribué/mandat clos (in-app + email), annonce publiée (in-app à tous les
actifs, pas d'email de masse), cotisations générées (in-app), demande d'adhésion
chorale traitée (email au contact, pas encore de compte). L'API
`/api/notifications/` est filtrée **par destinataire** (jamais par simple
appartenance chorale). Email : backend console en dev ; `EMAIL_BACKEND` + `EMAIL_*`
par variables d'environnement en prod.

Changement de mot de passe : `POST /api/auth/changer-mot-de-passe/`
`{ancien, nouveau}` (ancien requis, validateurs Django appliqués).

### Auth

JWT (djangorestframework-simplejwt). Le token embarque `groups`, `is_superuser`,
`chorale_nom`, `chorale_currency`, `membre_id`… décodés côté Angular (pas de
`/me/`). Nouveau claim utile au front → l'ajouter dans
`authentication/serializers.py` **et** dans `DecodedToken` côté frontend.

Access token : **30 minutes** (les rôles décodés côté front se rafraîchissent
au prochain refresh silencieux après un changement de mandat). La
**suspension d'une chorale** (`Chorale.is_active=False`, via l'admin) est
appliquée partout : login refusé, tokens déjà émis privés de toute donnée
(middleware), invitations invalidées.

Les groupes Django sont recalculés par `membres/signals.py` sur **toute**
sauvegarde de `Mandat` **ou** de `Membre` (création, changement de statut,
soft-delete/restore) — ne jamais toucher `user.groups` directement.

## Rapports & génération PDF (WeasyPrint)

L'app `rapports` agrège les autres apps (aucun modèle propre). 4 rapports :
financier (bureau/trésorier), présences / effectifs / répertoire (bureau/MDC).

- JSON : `GET /api/rapports/<type>/?date_debut=&date_fin=`
- Export : `?export=pdf` ou `?export=csv` (param `export`, **pas** `format` qui est
  réservé par DRF).

Le PDF utilise **WeasyPrint**, qui exige les libs système **GTK/Pango/Cairo** au
runtime :
- **Linux** : `apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`.
- **Windows** : installer GTK (p. ex. via MSYS2 : `pacman -S mingw-w64-ucrt-x86_64-gtk3`).
  Le code déclare automatiquement les emplacements DLL usuels
  (`C:\msys64\ucrt64\bin`, `mingw64\bin`, runtime GTK3) ; surchargeable via
  `WEASYPRINT_DLL_DIR`.

Si les libs manquent, l'endpoint PDF renvoie proprement **HTTP 503** (message
clair) au lieu de planter ; l'export CSV fonctionne partout.

## Tests

```bash
python manage.py test          # ou :
pytest -q                      # suite complète (pytest-django)
python manage.py check
```

Suite : ~129 tests couvrant auth, dashboard, isolation cross-tenant par app
(finances, membres, musique, présences), RBAC, structure (pupitres/postes/
organigramme), bulk actions, annonces, rapports (agrégation + exports +
dégradation PDF), demande d'adhésion chorale (throttle, honeypot, doublons,
modération admin), invitations choriste (génération, vérification,
inscription, expiration/quota, throttle) et synchronisation RBAC
(permissions fantômes, restore, suspension de chorale, mots de passe
faibles, matricules séquentiels), notifications (déclenchement par cas
métier, in-app + email, isolation par destinataire) et changement de mot
de passe. Fixtures partagées dans
`conftest.py` (`membre_factory`, `mandat_factory`, `chorale_a`/`chorale_b`,
`auth_client`).
