# Contribuer à Open Quiz

Merci de votre intérêt pour Open Quiz. Les corrections ciblées, tests,
traductions et améliorations de documentation sont les bienvenues.

## 📖 Sommaire

- [Avant de commencer](#-avant-de-commencer)
- [Préparer l’environnement de développement](#-préparer-lenvironnement-de-développement)
- [Préparer une branche](#-préparer-une-branche)
- [Principes de contribution](#-principes-de-contribution)
- [Selon la nature du changement](#-selon-la-nature-du-changement)
- [Vérifications](#-vérifications)
- [Ouvrir une pull request](#-ouvrir-une-pull-request)

## 👋 Avant de commencer

1. consultez les
   [issues ouvertes](https://github.com/guillaume-behr/open-quiz/issues) et les
   [pull requests](https://github.com/guillaume-behr/open-quiz/pulls) ;
2. ouvrez une issue avant une évolution importante, une transition de données
   ou un changement de comportement public ;
3. préparez l’[environnement de développement](#-préparer-lenvironnement-de-développement) ;
4. ne publiez jamais de secret, de donnée d’élève ou de vulnérabilité : utilisez
   la procédure privée de [SECURITY.md](SECURITY.md).

Une petite correction évidente peut être proposée directement. Pour une
fonctionnalité, décrivez d’abord le besoin utilisateur et les contraintes afin
d’éviter un travail incompatible avec la direction du projet.

## 🛠️ Préparer l’environnement de développement

Cette procédure sert au développement et à l’évaluation du projet. Pour
installer une instance à utiliser, suivez la procédure Docker du
[README](README.md#-installation).

### Prérequis

- Python 3.14 et [uv](https://docs.astral.sh/uv/) ;
- Node.js 24, Corepack et pnpm 11 ;
- Docker avec le plugin Compose, pour PostgreSQL ;
- Git.

> [!NOTE]
> Sous Windows, exécutez ces commandes dans WSL : les scripts demandent un shell
> compatible POSIX.

### Base de données et secrets

Depuis la racine du dépôt :

```shell
sh ./install-dev.sh
```

Le script crée `open-quiz-backend/.env` avec des secrets distincts, affiche les
identifiants administrateur une seule fois et lance uniquement le service Docker
`open-quiz-database`. Il conserve un `.env` de développement existant et
compatible, refuse les valeurs d’exemple et les configurations de production,
puis vérifie que PostgreSQL accepte réellement les identifiants.

Le service est démarré avec `docker-compose.dev.yml`, qui publie PostgreSQL sur
`127.0.0.1:5432`. Cette surcharge est indispensable au développement : le réseau
Compose de production est interne, et Docker n’y publie aucun port. Sans elle,
l’API lancée sur la machine échoue avec « connection refused ».

Le script crée enfin le rôle et la base `open_quiz_test`, que la suite de tests
backend utilise. Elle y crée et supprime un schéma par module, sans jamais
toucher aux données de développement. Définissez `TEST_DATABASE_URL` pour viser
un autre serveur PostgreSQL.

### API

```shell
cd open-quiz-backend
uv sync
uv run fastapi dev main.py
```

L’API répond sur `http://localhost:8000` et sa documentation interactive est
disponible sur `http://localhost:8000/docs`.

### Interface

Dans un second terminal, depuis la racine du dépôt :

```shell
cd open-quiz-frontend
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrez `http://localhost:5173`. Le serveur de développement transmet
automatiquement les requêtes `/api` au backend.

## 🌿 Préparer une branche

Créez une branche courte depuis la branche par défaut à jour :

```shell
git switch master
git pull --ff-only
git switch -c type/description-courte
```

Préfixes suggérés : `fix/`, `feat/`, `docs/`, `test/`, `refactor/` ou `chore/`.

## 🧭 Principes de contribution

- limitez chaque pull request à un problème cohérent ;
- conservez les interfaces existantes, sauf changement discuté et documenté ;
- gardez les règles métier et les autorisations côté backend ;
- ajoutez un test ciblé pour toute correction de comportement ;
- ne modifiez les fichiers de verrouillage que lorsqu’une dépendance change ;
- ne modifiez pas `public/pyodide` sans documenter la provenance et la procédure
  de mise à jour ;
- ne mélangez jamais données réelles et jeux de test ;
- utilisez des messages de commit compréhensibles. Conventional Commits est
  accepté sans être obligatoire.

## 🗂️ Selon la nature du changement

### API, données et sécurité

- validez les entrées côté backend, même si le frontend les contrôle déjà ;
- vérifiez les permissions avec les rôles administrateur, enseignant et élève ;
- préservez l’atomicité des imports et opérations concurrentes ;
- accompagnez toute évolution du schéma PostgreSQL d’une stratégie explicite
  de déploiement et des tests correspondants ;
- documentez les changements d’API, de configuration, de conservation ou de
  sécurité ;
- signalez tout changement visible ou incompatible dans la description de la
  pull request, afin qu’il figure dans les notes de la release.

### Interface et accessibilité

- utilisez les composants et styles déjà présents ;
- conservez la navigation au clavier, les libellés accessibles, les états de
  focus et la réduction des animations ;
- vérifiez au minimum les tailles mobile et bureau ;
- ajoutez une capture à la pull request lorsqu’elle facilite la revue ;
- exécutez les tests Playwright lorsque le parcours utilisateur change.

### Traductions

Toute nouvelle chaîne visible doit exister dans les huit catalogues de
`open-quiz-frontend/public/locales`.

- l’anglais est la référence structurelle des clés ;
- conservez exactement les variables `{{...}}` et les suffixes de pluriel ;
- exécutez `pnpm test` pour contrôler les catalogues ;
- pour ajouter une langue, suivez la section internationalisation du
  [README frontend](open-quiz-frontend/README.md#-internationalisation).

### Documentation

- utilisez des chemins et commandes réellement présents dans le dépôt ;
- évitez de dupliquer les détails d’exploitation dans plusieurs fichiers ;
- vérifiez les liens relatifs et les ancres ;
- documentez un fait au seul endroit qui en est responsable, et renvoyez-y
  depuis les autres.

## ✅ Vérifications

Exécutez les contrôles correspondant aux fichiers modifiés. Les mêmes contrôles
principaux sont exécutés par
[GitHub Actions](https://github.com/guillaume-behr/open-quiz/actions/workflows/security.yml),
qui fait autorité pour les contrôles obligatoires. Chaque bloc ci-dessous
part de la racine du dépôt ; revenez-y avant de passer à un autre composant.

### Backend

```shell
cd open-quiz-backend
uv sync --frozen --dev
uv run --frozen ruff check app tests main.py scripts
uv run --frozen ruff check --select S app main.py scripts
uv run --frozen ruff format --check app tests main.py scripts
uv run --frozen pytest -q
uv run --frozen pip-audit
```

### Frontend

```shell
cd open-quiz-frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check
pnpm test
pnpm typecheck
pnpm build
pnpm audit --audit-level low
```

Pour un parcours utilisateur ou une modification du proxy HTTP/WebSocket :

```shell
pnpm exec playwright install chromium
pnpm test:e2e
```

### Conteneurs et déploiement

Après une modification de Docker, Caddy, Compose ou des variables de
production :

```shell
test -f open-quiz-backend/.env || \
    cp open-quiz-backend/.env.production.example open-quiz-backend/.env
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
docker compose build
```

N’utilisez ces valeurs d’exemple que pour valider la structure. Une instance
réelle exige des secrets robustes et distincts.

## 🔀 Ouvrir une pull request

Avant l’envoi :

- relisez le diff complet et retirez les changements sans rapport ;
- vérifiez qu’aucun secret, fichier `.env`, jeton ou donnée personnelle n’est
  présent ;
- décrivez le problème, la solution, les risques et les compromis ;
- indiquez les commandes réellement exécutées et leur résultat ;
- mentionnez les tests ajoutés, les évolutions de schéma et les changements de
  documentation ;
- liez l’issue avec `Closes #…` lorsqu’elle doit être fermée à la fusion.

Une revue peut demander de réduire le périmètre, d’ajouter un test ou de
documenter une décision. Les échanges doivent rester factuels et respectueux.

En contribuant, vous acceptez que votre contribution soit distribuée sous la
[licence MIT](LICENSE) du projet.
