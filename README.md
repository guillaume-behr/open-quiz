# Open Quiz

Open Quiz est une plateforme libre et auto-hébergeable de quiz en classe. Les
enseignants préparent des banques de questions, organisent leurs classes,
lancent des sessions chronométrées et corrigent les réponses rédactionnelles.
Les élèves rejoignent une session avec un code et leur identifiant de classe,
sans créer de compte.

> **Statut : préversion 0.1.0.** Le projet est fonctionnel et testé, mais son
> schéma de données et ses interfaces peuvent encore évoluer avant la version
> 1.0. Les sauvegardes restent indispensables avant chaque mise à jour.

## ✨ Fonctionnalités

- comptes enseignant administrés avec mots de passe Argon2 et authentification
  TOTP obligatoire ;
- classes, élèves et niveaux, avec import et export JSON ;
- banques de questions à choix unique, multiple ou réponse rédactionnelle ;
- images privées, extraits de code et réponses attendues en langage indiqué ;
- composition aléatoire des quiz par niveau de difficulté ;
- sessions chronométrées avec pause, reprise, surveillance et retour optionnel
  aux questions précédentes ;
- notation automatique et correction manuelle des réponses rédactionnelles ;
- interface claire/sombre traduite en français, anglais, allemand, espagnol,
  portugais, ukrainien, arabe et chinois simplifié ;
- exécution locale et interrompable de courts extraits Python avec Pyodide ;
- déploiement Docker durci derrière Caddy, avec SQLite persistant.

## 🧰 Pile technique

| Partie | Technologies |
| --- | --- |
| API | Python 3.14, FastAPI, SQLAlchemy, SQLite |
| Sécurité | JWT courts, cookies HttpOnly rotatifs, TOTP, Argon2, Fernet |
| Interface | React 19, TypeScript, Vite, Tailwind CSS |
| Exécution Python | Pyodide dans un Web Worker |
| Production | Docker Compose, Caddy |
| Qualité | pytest, Ruff, ESLint, Prettier, TypeScript |

## Prérequis

Pour le développement local :

- Python 3.14 ;
- [uv](https://docs.astral.sh/uv/) ;
- Node.js 24 ;
- Corepack et pnpm 11 (la version exacte est déclarée dans `package.json`).

Docker avec le plugin Compose est requis uniquement pour le déploiement
conteneurisé.

## 🚀 Installation locale

### 1. API

Depuis `open-quiz-backend`, copiez `.env.example` vers `.env`, puis remplacez
les trois valeurs `replace-with-...`.

```shell
cd open-quiz-backend
uv sync
uv run fastapi dev main.py
```

L’API écoute sur `http://localhost:8000`. En développement, OpenAPI est
disponible sur `http://localhost:8000/docs`.

### 2. Interface

Dans un second terminal :

```shell
cd open-quiz-frontend
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrez `http://localhost:5173`. Le proxy Vite transmet `/api` au backend.

## ⚙️ Configuration

Les secrets appartiennent uniquement à `open-quiz-backend/.env`, ignoré par
Git. Les modèles fournis ne contiennent aucune vraie donnée sensible.

| Variable | Rôle | Valeur de développement |
| --- | --- | --- |
| `DATABASE_URL` | URL SQLAlchemy de la base | `sqlite:///./open-quiz.db` |
| `JWT_SECRET` | Signature des jetons ; 32 caractères minimum | obligatoire |
| `TOTP_ENCRYPTION_KEY` | Chiffrement TOTP ; distinct du secret JWT, 32 caractères minimum | obligatoire |
| `ADMIN_USERNAME` | Identifiant du compte administrateur géré | `admin` |
| `ADMIN_PASSWORD` | Mot de passe administrateur ; 16 caractères minimum | obligatoire |
| `FRONTEND_ORIGIN` | Origine HTTP(S) exacte, sans `/` final | `http://localhost:5173` |
| `ACCESS_TOKEN_MINUTES` | Durée d’un jeton d’accès, de 1 à 30 min | `15` |
| `REFRESH_TOKEN_DAYS` | Durée maximale d’une session, de 1 à 30 jours | `7` |
| `LOGIN_ATTEMPTS` | Tentatives d’authentification par fenêtre | `5` |
| `LOGIN_WINDOW_SECONDS` | Fenêtre de limitation des connexions | `900` |
| `QUIZ_JOIN_ATTEMPTS` | Tentatives publiques pour rejoindre un quiz | `20` |
| `QUIZ_PARTICIPANT_ATTEMPTS` | Requêtes d’un participant par fenêtre | `240` |
| `QUIZ_VIOLATION_ATTEMPTS` | Alertes de surveillance par fenêtre | `20` |
| `QUIZ_RATE_WINDOW_SECONDS` | Fenêtre des limites publiques | `60` |
| `QUIZ_RESULT_RETENTION_DAYS` | Conservation des résultats terminés | `365` |
| `MAX_REQUEST_BODY_BYTES` | Taille des requêtes ordinaires | `65536` |
| `APP_ENV` | `development`, `test` ou `production` | `development` |

Le frontend reconnaît aussi `VITE_API_URL`. Laissez cette valeur vide pour le
proxy Vite et le déploiement Caddy fourni. Une origine absolue est utile
uniquement lorsque l’API est servie séparément et que CORS est configuré avec
la même origine frontend.

## Parcours principal

1. L’administrateur se connecte et inscrit son application TOTP.
2. Il crée un compte enseignant.
3. L’enseignant configure à son tour TOTP, crée une classe puis ses élèves.
4. Il prépare des banques de questions et compose un quiz.
5. Il lance une salle d’attente pour une classe.
6. Les élèves rejoignent la session avec le code et leur identifiant.
7. L’enseignant démarre le quiz, puis consulte et corrige les résultats.

## Commandes de qualité

Backend :

```shell
cd open-quiz-backend
uv run ruff check app tests main.py scripts
uv run ruff format --check app tests main.py scripts
uv run pytest -q
```

Pour appliquer le formatage Python :

```shell
uv run ruff format app tests main.py scripts
```

Frontend :

```shell
cd open-quiz-frontend
pnpm lint
pnpm format:check
pnpm test
pnpm typecheck
pnpm build
pnpm audit --prod --audit-level low
```

`pnpm test` contrôle l’intégrité des huit catalogues de traduction et de leurs
variables d’interpolation. `pnpm format` applique Prettier aux sources et aux
catalogues.

## 🏗️ Architecture

```text
Navigateur
  ├─ espace public élève
  ├─ espace enseignant
  └─ espace administrateur
          │ HTTPS / JSON
          ▼
Caddy (SPA, CSP, ressources statiques, proxy /api)
          │ réseau Docker interne
          ▼
FastAPI (authentification, règles métier, limites de débit)
          │
          ▼
SQLite en mode WAL (volume persistant)
```

Le backend conserve les règles d’autorisation, les tirages de questions, la
notation et les limites de débit. Le frontend garde les jetons d’accès en
mémoire ; seuls les cookies de session rotatifs sont HttpOnly. Les jetons de
participation élève restent dans `sessionStorage` afin de survivre à un
rechargement de l’onglet. Les fichiers `public/pyodide` sont des ressources
vendoriées nécessaires à l’exécution Python hors ligne.

## Structure

```text
.
├── .github/                 CI, Dependabot et modèles de contribution
├── open-quiz-backend/
│   ├── app/                 configuration, modèles, sécurité et routes API
│   ├── scripts/             récupération 2FA et rotation de secrets locaux
│   └── tests/               tests d’API, sécurité et migrations SQLite
├── open-quiz-frontend/
│   ├── public/locales/      huit catalogues de traduction
│   ├── public/pyodide/      runtime Python navigateur vendorié
│   ├── scripts/             validations propres au frontend
│   └── src/                 API cliente, pages et composants React
├── docker-compose.yml       déploiement autonome
├── update.ps1               mise à jour Windows
└── update.sh                mise à jour Unix
```

## 📦 Build et déploiement

La compilation locale du frontend écrit dans `open-quiz-frontend/dist` :

```shell
cd open-quiz-frontend
pnpm build
pnpm preview
```

Pour le déploiement fourni :

1. copiez `open-quiz-backend/.env.production.example` vers
   `open-quiz-backend/.env` ;
2. configurez une origine HTTPS exacte et trois secrets robustes ;
3. sauvegardez `TOTP_ENCRYPTION_KEY` dans un gestionnaire de secrets ;
4. validez puis démarrez les conteneurs.

```shell
docker compose config --quiet
docker compose up --detach --build --remove-orphans --wait
docker compose ps
```

Le frontend est lié à `127.0.0.1:7800`. Placez-le derrière un reverse proxy
HTTPS public :

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Vérifiez ensuite :

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est `{"status":"ok"}`. Les mises à jour en avance rapide
peuvent être appliquées avec `update.ps1` ou `sh ./update.sh`.

## Exploitation et sauvegardes

- surveillez `/api/health`, l’espace disque et le certificat TLS ;
- sauvegardez régulièrement le volume `open-quiz-data` avec un outil compatible
  SQLite WAL ou pendant un arrêt contrôlé ;
- conservez `TOTP_ENCRYPTION_KEY` : sa perte impose une nouvelle inscription
  TOTP pour chaque compte ;
- centralisez les événements JSON `security.*`,
  `auth.login_rate_limited` et `auth.refresh_reuse_detected` ;
- testez une restauration avant de considérer une sauvegarde comme valide.

## 🛠️ Dépannage

- **L’API refuse de démarrer :** vérifiez les longueurs des secrets, leur
  différence, `APP_ENV` et l’absence de `/` final dans `FRONTEND_ORIGIN`.
- **Le navigateur bloque les appels API :** l’origine visible dans le
  navigateur doit correspondre exactement à `FRONTEND_ORIGIN`.
- **Un enseignant a perdu son authentificateur :** utilisez « Récupérer
  l’accès » dans l’administration ou
  `uv run python -m scripts.reset_two_factor identifiant`.
- **Le frontend ne trouve pas le backend :** démarrez l’API sur le port 8000 ou
  configurez `VITE_API_URL`.
- **Docker ne devient pas sain :** consultez `docker compose ps` puis
  `docker compose logs open-quiz-backend open-quiz-frontend`.

## 🤝 Contribution et sécurité

Consultez [CONTRIBUTING.md](CONTRIBUTING.md) avant de proposer un changement.

Ne publiez pas une vulnérabilité dans une issue. Suivez la procédure privée de
[SECURITY.md](SECURITY.md).

## Licence

Open Quiz est distribué sous licence MIT. Voir [LICENSE](LICENSE).

## Remerciements

Le projet s’appuie notamment sur FastAPI, React, Pyodide, Caddy et les nombreux
projets libres référencés dans les fichiers de verrouillage.
