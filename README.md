<h1><img src=".github/assets/open-quiz-wordmark.svg" alt="Open Quiz" width="230"></h1>

[![CI](https://github.com/guillaume-behr/open-quiz/actions/workflows/security.yml/badge.svg)](https://github.com/guillaume-behr/open-quiz/actions/workflows/security.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Plateforme libre et auto-hébergeable pour créer des quiz, organiser des examens
en classe et proposer des entraînements aux élèves.

Open Quiz réunit trois espaces dans une même application : l’administrateur
gère les enseignants, les enseignants préparent les contenus et les sessions,
et les élèves passent leurs examens ou s’entraînent depuis leur tableau de bord.

> [!IMPORTANT]
> **Préversion 0.2.1.** Le projet est fonctionnel et testé, mais son schéma de
> données et ses interfaces peuvent encore évoluer avant la version 1.0.
> Sauvegardez vos données avant chaque mise à jour et consultez le
> [journal des versions](CHANGELOG.md).

## Sommaire

- [Pourquoi Open Quiz](#pourquoi-open-quiz)
- [Installation avec Docker](#installation-avec-docker)
- [Premiers pas](#premiers-pas)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Développement local](#développement-local)
- [Développement et qualité](#développement-et-qualité)
- [Documentation et contribution](#documentation-et-contribution)

## Pourquoi Open Quiz

### Examens et entraînements

- examens chronométrés avec salle d’attente, pause, reprise et rattrapage ;
- banques d’entraînement attribuées par classe et relançables librement ;
- tirage commun à la classe ou individuel, selon le quiz ;
- sujets papier nominatifs avec mise en page A4 et tirage déterministe.

### Questions et correction

- choix unique, choix multiple et réponse rédactionnelle ;
- images privées, extraits de code et réponses attendues dans un langage donné ;
- barème défini réponse par réponse, avec points négatifs facultatifs ;
- correction automatique ou manuelle, publication des notes et export CSV.

### Expérience élève

- compte personnel et tableau de bord dédié ;
- correction immédiate et historique de progression pour les entraînements ;
- interface claire ou sombre disponible en huit langues ;
- traduction locale facultative des quiz lorsque le navigateur la prend en
  charge ;
- exécution locale de courts extraits Python avec Pyodide.

### Hébergement maîtrisé

- déploiement autonome avec Docker Compose, Caddy et PostgreSQL ;
- mots de passe Argon2, TOTP pour les comptes privilégiés et cookies HttpOnly ;
- limites de débit, journaux de sécurité et données persistantes sauvegardables.

Le déroulement général reste simple :

1. l’administrateur crée les comptes enseignants ;
2. l’enseignant crée ses élèves, ses classes et ses banques de questions ;
3. il prépare un examen ou ouvre des banques à l’entraînement ;
4. les élèves se connectent et rejoignent leur activité ;
5. l’enseignant corrige les réponses rédactionnelles puis publie ou exporte les
   résultats.

## Installation avec Docker

Docker Compose est la méthode recommandée pour installer et utiliser Open Quiz.
Cette section couvre le premier démarrage. Pour les sauvegardes, les mises à
jour, la rotation des secrets et le dépannage, consultez le
[guide de déploiement et d’exploitation](docs/deployment.md).

### Prérequis

- Docker avec le plugin Compose ;
- Git et un shell compatible POSIX (Linux, macOS ou WSL sous Windows) ;
- un nom de domaine valide, ainsi qu’un reverse proxy HTTPS pour rendre
  l’instance publique.

### Récupérer le projet

```shell
git clone https://github.com/guillaume-behr/open-quiz.git
cd open-quiz
```

### Lancer les conteneurs

Depuis la racine du dépôt, lancez l’installation guidée :

```shell
sh ./install.sh
```

Le script demande uniquement le nom de domaine, sans `https://` ni `/` final.
Il génère automatiquement tous les secrets et le mot de passe administrateur,
crée `open-quiz-backend/.env` avec les variables de production, puis lance
`update.sh` pour construire et démarrer les conteneurs. Enregistrez le mot de
passe administrateur affiché une seule fois.

Le domaine peut aussi être passé en argument, ce qui permet une installation
non interactive :

```shell
sh ./install.sh --domain quiz.example.com
```

`sh ./install.sh --help` décrit les options disponibles. Le script vérifie le
domaine et l’absence de configuration existante avant de contrôler Docker, et
n’écrit aucun secret tant que ces vérifications n’ont pas abouti.

Le script refuse d’écraser une configuration existante. Pour un déploiement
déjà installé, utilisez directement `sh ./update.sh`. Renseignez ensuite dans
`.env` les informations légales, de confidentialité et d’accessibilité propres
à votre instance, puis relancez `sh ./update.sh`.

L’installation configure Open Quiz, mais pas le DNS, le certificat TLS ou le
reverse proxy de la machine. Ces éléments restent à mettre en place pour rendre
le domaine accessible en HTTPS.

Le frontend écoute uniquement sur `127.0.0.1:7800`. Publiez-le derrière un
reverse proxy HTTPS, par exemple avec Caddy :

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Un [exemple de configuration Nginx](deployment/nginx.conf) est également
fourni ; remplacez son domaine et ses chemins de certificats avant de l'activer.

Vérifiez ensuite l’instance :

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est `{"status":"ok"}`.

### Mises à jour et sauvegardes

- utilisez `sh ./update.sh` sous Unix ou `./update.ps1` sous PowerShell pour
  appliquer une mise à jour en avance rapide et reconstruire les conteneurs ;
- ajoutez `--no-pull` (ou `-NoPull` sous PowerShell) pour reconstruire et
  redémarrer sans récupérer de nouvelle révision ;
- les scripts refusent de continuer si le dépôt contient des modifications
  locales, affichent la version avant et après la mise à jour, et rappellent de
  sauvegarder la base lorsque la révision change ;
- sauvegardez régulièrement PostgreSQL avec `pg_dump` et testez les restaurations ;
- conservez `TOTP_ENCRYPTION_KEY` et `STUDENT_CREDENTIAL_ENCRYPTION_KEY` dans un
  gestionnaire de secrets ;
- testez la restauration de vos sauvegardes ;
- sauvegardez impérativement la base avant une mise à jour de version.

Le passage à PostgreSQL réinitialise le stockage : aucune reprise de la base
historique n’est fournie. Consultez le [journal des versions](CHANGELOG.md).

## Premiers pas

Les chemins ci-dessous sont à ajouter au domaine configuré pendant
l’installation. En développement local, utilisez `http://localhost:5173`.

| Espace         | Chemin              | Première action                                                                      |
| -------------- | ------------------- | ------------------------------------------------------------------------------------ |
| Administration | `/admin/dashboard`  | Se connecter avec les identifiants de `.env`, configurer TOTP et créer un enseignant |
| Enseignant     | `/teacher/login`    | Configurer TOTP, puis créer les élèves, classes et banques                           |
| Élève          | `/student/login`    | Se connecter avec le compte fourni par l’enseignant                                  |

La racine de l’application redirige vers la connexion élève. Les tableaux de
bord protégés renvoient vers leur écran de connexion lorsque la session est
absente ou expirée.

Les questions sont tirées au lancement d’une session, pas à la création du
quiz. L’enseignant peut choisir un tirage commun à la classe ou un tirage
individuel. Les questions, leur ordre et le barème sont ensuite figés pour
préserver la correction historique, même si la banque évolue.

## Configuration

Les secrets du backend sont stockés dans `open-quiz-backend/.env`, ignoré par
Git. Les principales variables sont :

| Variable                            | Rôle                                               | Exemple de développement   |
| ----------------------------------- | -------------------------------------------------- | -------------------------- |
| `DATABASE_URL`                      | Base PostgreSQL via SQLAlchemy                     | `postgresql+psycopg://…`   |
| `POSTGRES_PASSWORD`                 | Mot de passe du rôle PostgreSQL                    | obligatoire                |
| `JWT_SECRET`                        | Signature des jetons, 32 caractères minimum        | obligatoire                |
| `TOTP_ENCRYPTION_KEY`               | Chiffrement TOTP, distinct du secret JWT           | obligatoire                |
| `STUDENT_CREDENTIAL_ENCRYPTION_KEY` | Chiffrement des mots de passe élèves récupérables  | obligatoire                |
| `ADMIN_USERNAME`                    | Identifiant administrateur                         | `admin`                    |
| `ADMIN_PASSWORD`                    | Mot de passe administrateur, 16 caractères minimum | obligatoire                |
| `FRONTEND_ORIGIN`                   | Origine HTTP(S) exacte, sans `/` final             | `http://localhost:5173`    |
| `APP_ENV`                           | `development`, `test` ou `production`              | `development`              |

Les fichiers [`open-quiz-backend/.env.example`](open-quiz-backend/.env.example)
et
[`open-quiz-backend/.env.production.example`](open-quiz-backend/.env.production.example)
listent toutes les variables disponibles. Le
[guide de déploiement](docs/deployment.md#configurer-la-conservation-et-les-limites)
explique les limites et les durées de conservation.

Le frontend accepte aussi `VITE_API_URL`. Laissez cette variable vide avec le
proxy Vite ou le déploiement Caddy fourni. Utilisez une URL absolue uniquement
si l’API est servie sur une autre origine, avec la configuration CORS et CSP
correspondante.

> [!CAUTION]
> L’auto-hébergement ne vaut ni homologation, ni conformité automatique. Avant
> une mise en service, faites valider la base légale, les durées de conservation,
> les sous-traitants et l’information des utilisateurs par l’établissement ou
> son DPO. Conservez la mention « Accessibilité : non conforme » tant qu’aucun
> audit RGAA complet n’a été réalisé.

## Architecture

| Partie            | Technologies principales                               |
| ----------------- | ------------------------------------------------------ |
| API               | Python 3.14, FastAPI, SQLAlchemy, PostgreSQL           |
| Interface         | React 19, TypeScript, Vite, Tailwind CSS               |
| Sécurité          | JWT, cookies HttpOnly, TOTP, Argon2, Fernet            |
| Python navigateur | Pyodide dans un Web Worker                             |
| Production        | Docker Compose et Caddy                                |
| Qualité           | pytest, Ruff, ESLint, Prettier, TypeScript, Playwright |

```text
Navigateur (élève, enseignant ou administrateur)
          │ HTTPS
          ▼
Reverse proxy TLS de l’hôte
          │ HTTP sur 127.0.0.1:7800
          ▼
Caddy (SPA, CSP, fichiers statiques, proxy /api)
          │ réseau Docker interne
          ▼
FastAPI (authentification, règles métier, limites de débit)
          │
          ▼
PostgreSQL (volume persistant)
```

### Structure du dépôt

```text
.
├── .github/                 CI, Dependabot et modèles de contribution
├── docs/                    guides de déploiement et d’exploitation
├── open-quiz-backend/       API FastAPI, scripts et tests
├── open-quiz-frontend/      application React, traductions et tests E2E
├── scripts/                 fonctions communes aux scripts shell
├── CHANGELOG.md             historique des versions
├── CONTRIBUTING.md          guide de contribution
├── docker-compose.yml       déploiement autonome
├── install-dev.sh           préparation de l’environnement de développement
├── install.sh               installation Docker guidée sous Unix
├── SECURITY.md              signalement privé des vulnérabilités
├── update.ps1               mise à jour sous PowerShell
└── update.sh                mise à jour sous Unix
```

## Développement local

Les commandes de cette section sont destinées au développement et à
l’évaluation du projet. Pour installer une instance à utiliser, suivez en
priorité la procédure [Docker](#installation-avec-docker).

### Prérequis de développement

- Python 3.14 et [uv](https://docs.astral.sh/uv/) ;
- Node.js 24, Corepack et pnpm 11 ;
- Docker avec le plugin Compose, pour PostgreSQL ;
- Git.

### Démarrer l’API

Depuis la racine du dépôt, générez les identifiants de développement et
démarrez PostgreSQL :

```shell
sh ./install-dev.sh
```

Le script crée `open-quiz-backend/.env` avec des secrets distincts, affiche les
identifiants administrateur une seule fois et lance uniquement le service
Docker `open-quiz-database`. Il conserve un `.env` de développement existant et
compatible, refuse les valeurs d’exemple et les configurations de production,
puis vérifie que PostgreSQL accepte réellement les identifiants.

Le service est démarré avec `docker-compose.dev.yml`, qui publie PostgreSQL sur
`127.0.0.1:5432`. Cette surcharge est indispensable au développement : le
réseau Compose de production est interne, et Docker n’y publie aucun port. Sans
elle, l’API lancée sur la machine échoue avec « connection refused ».

```shell
cd open-quiz-backend
uv sync
uv run fastapi dev main.py
```

L’API répond sur `http://localhost:8000` et sa documentation interactive est
disponible sur `http://localhost:8000/docs`.

> [!NOTE]
> Sous Windows, exécutez le script dans WSL.

### Démarrer l’interface

Dans un second terminal, depuis la racine du dépôt :

```shell
cd open-quiz-frontend
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrez `http://localhost:5173`. Le serveur de développement transmet
automatiquement les requêtes `/api` au backend.

## Développement et qualité

### Backend

```shell
cd open-quiz-backend
uv sync --frozen --dev
uv run ruff check app tests main.py scripts
uv run ruff format --check app tests main.py scripts
uv run pytest -q
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
```

Les tests navigateur sont disponibles séparément :

```shell
pnpm exec playwright install chromium
pnpm test:e2e
```

Les mêmes contrôles principaux sont exécutés par
[GitHub Actions](https://github.com/guillaume-behr/open-quiz/actions/workflows/security.yml).

## Documentation et contribution

| Ressource                                              | Contenu                                            |
| ------------------------------------------------------ | -------------------------------------------------- |
| [Déploiement et exploitation](docs/deployment.md)      | production, sauvegardes, mises à jour et dépannage |
| [Documentation backend](open-quiz-backend/README.md)   | API, sécurité, stockage et exploitation            |
| [Documentation frontend](open-quiz-frontend/README.md) | interface, routes, traduction et tests navigateur  |
| [Journal des versions](CHANGELOG.md)                   | nouveautés et transitions incompatibles            |
| [Guide de contribution](CONTRIBUTING.md)               | conventions et vérifications attendues             |
| [Politique de sécurité](SECURITY.md)                   | procédure privée de signalement                    |

Les corrections ciblées, tests, traductions et améliorations de documentation
sont les bienvenues. Pour une évolution importante, ouvrez d’abord une issue afin
d’échanger sur le besoin et l’approche.

Ne publiez jamais une vulnérabilité, un secret ou des données d’élève dans une
issue publique. Suivez la procédure décrite dans [SECURITY.md](SECURITY.md).

Open Quiz est distribué sous [licence MIT](LICENSE).

## Remerciements

Open Quiz s’appuie notamment sur FastAPI, React, Pyodide, Caddy et les nombreux
projets libres référencés dans ses fichiers de verrouillage.
