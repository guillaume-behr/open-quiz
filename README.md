<h1><img src=".github/assets/open-quiz-wordmark.svg" alt="Open Quiz" width="230"></h1>

Plateforme libre et auto-hébergeable pour organiser des quiz en classe.

Les enseignants créent les comptes élèves, leurs classes et leurs questions,
lancent des examens chronométrés et rendent des banques de questions disponibles
pour l’entraînement de chaque classe. Les élèves se connectent à leur tableau de
bord pour rejoindre un examen ou démarrer un entraînement.

> [!IMPORTANT]
> **Préversion 0.2.0.** Le projet est fonctionnel et testé, mais son schéma de
> données et ses interfaces peuvent évoluer avant la version 1.0. Sauvegardez
> vos données avant chaque mise à jour.

Consultez le [journal des versions](CHANGELOG.md) pour les nouveautés et les
changements incompatibles.

## 🧭 Sommaire

- [Démarrage rapide](#démarrage-rapide)
- [Fonctionnement](#fonctionnement)
- [Routes de l’interface](#routes-de-linterface)
- [Fonctionnalités](#fonctionnalités)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Tests et qualité](#tests-et-qualité)
- [Déploiement](#déploiement)
- [Exploitation et sauvegardes](#exploitation-et-sauvegardes)
- [Dépannage](#dépannage)
- [Contribution, sécurité et licence](#contribution-sécurité-et-licence)

## 🚀 Démarrage rapide

### Prérequis

- Python 3.14 et [uv](https://docs.astral.sh/uv/) ;
- Node.js 24, Corepack et pnpm 11 ;
- Docker avec le plugin Compose, uniquement pour le déploiement conteneurisé.

### 1. Démarrer l’API

Copiez `open-quiz-backend/.env.example` vers `open-quiz-backend/.env`, puis
remplacez les trois valeurs `replace-with-...`.

```shell
cd open-quiz-backend
chmod 600 .env
uv sync
uv run fastapi dev main.py
```

L’API est disponible sur `http://localhost:8000`. Sa documentation OpenAPI se
trouve sur `http://localhost:8000/docs` en développement.

### 2. Démarrer l’interface

Dans un second terminal :

```shell
cd open-quiz-frontend
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrez `http://localhost:5173`. La racine redirige vers la connexion élève. Le
serveur Vite transmet automatiquement les requêtes `/api` au backend.

Pour la première configuration, utilisez directement l’espace adapté :

- enseignant : `http://localhost:5173/teacher/login` ;
- administrateur : `http://localhost:5173/admin/dashboard` ;
- élève : `http://localhost:5173/student/login`.

## 🎯 Fonctionnement

1. L’administrateur se connecte, configure TOTP et crée les comptes enseignants.
2. L’enseignant configure TOTP, crée les comptes dans l’onglet **Élèves**, puis
   les affecte depuis l’onglet **Classes**.
3. Il alimente ses banques avec des questions faciles, moyennes ou difficiles.
   Il attribue les points directement à chaque réponse, y compris des valeurs
   négatives si nécessaire.
4. Il crée les examens en indiquant le nombre de questions voulu pour chaque
   difficulté et choisit, pour chaque classe, les banques accessibles en
   entraînement.
5. Pour un examen, il choisit si les points négatifs doivent être pris en
   compte, configure le tirage, sélectionne une classe et ouvre la salle
   d’attente.
6. L’élève se connecte à son compte et saisit uniquement le code de l’examen.
7. L’enseignant démarre la session, consulte les résultats, corrige les réponses
   rédactionnelles et peut exporter les notes au format CSV.

Les questions sont tirées au lancement, jamais lors de la création du quiz. Un
tirage commun utilise le même ensemble de questions et le même barème pour tous,
mais l’ordre est mélangé et mémorisé séparément pour chaque élève. Un tirage
individuel sélectionne un ensemble distinct pour chaque élève affecté à la
classe.

Une banque autorisée est disponible à tout moment dans le tableau de bord des
élèves de la classe. Un nouveau tirage est effectué à chaque démarrage, sans
points ni note, et la bonne réponse apparaît après chaque question.

Si la langue d’un élève diffère de celle du quiz, il peut demander une
traduction automatique ou conserver le texte original.

## 🧭 Routes de l’interface

| Espace | Route | Usage |
| --- | --- | --- |
| Élève | `/student/login` | Connexion par identifiant et mot de passe |
| Élève | `/student/dashboard` | Accès aux examens et aux entraînements |
| Élève | `/student/exam` | Participation à un examen avec son code |
| Élève | `/student/training` | Exécution d’un entraînement libre |
| Enseignant | `/teacher/login` | Connexion enseignant et validation TOTP |
| Enseignant | `/teacher/dashboard` | Élèves, classes, quiz, banques et résultats |
| Administrateur | `/admin/dashboard` | Gestion des comptes enseignants |

La route `/` redirige vers `/student/login`. Les tableaux de bord protégés
renvoient vers leur écran de connexion lorsque la session correspondante est
absente ou expirée.

## ✨ Fonctionnalités

### Pour les enseignants

- création, modification, désactivation et suppression des comptes élèves ;
- gestion séparée des classes et affectation d’un compte élève à une classe ;
- banques de questions à choix unique, choix multiple ou réponse rédactionnelle ;
- images privées, extraits de code et réponses attendues dans un langage donné ;
- examens créés dans leur onglet et banques d’entraînement affectées par classe ;
- composition par quantité de questions faciles, moyennes et difficiles, avec
  plafonnement selon la disponibilité des banques sélectionnées ;
- barème défini réponse par réponse ; les réponses sélectionnées sont
  additionnées et les valeurs négatives sont activées par quiz ;
- tirage effectué au lancement, commun ou individuel selon la configuration ;
- sessions chronométrées avec pause, reprise et retour optionnel aux questions ;
- notation automatique et correction manuelle des réponses rédactionnelles ;
- export CSV des résultats d’une classe, pour un quiz précis ou pour tous ses
  quiz terminés.

L’export des résultats contient une ligne par participation : classe, quiz,
date, identifiant et nom de l’élève, progression, score, corrections manuelles
en attente et nombre d’incidents. Les fichiers UTF-8 sont directement
exploitables dans un tableur.

### Pour les élèves

- connexion avec un compte créé par l’enseignant ;
- tableau de bord séparant l’entrée en examen des entraînements disponibles ;
- entrée en examen avec le seul code de session après authentification ;
- entraînements relançables librement, sans note et avec correction immédiate ;
- interface claire ou sombre ;
- français, anglais, allemand, espagnol, portugais, ukrainien, arabe et chinois
  simplifié ;
- traduction facultative des quiz ;
- exécution locale et interrompable de courts extraits Python avec Pyodide.

### Sécurité et hébergement

- mots de passe Argon2 pour tous les comptes et TOTP obligatoire pour les
  enseignants et administrateurs ;
- jetons d’accès courts et cookies HttpOnly rotatifs ;
- limites de débit sur les routes sensibles ;
- déploiement Docker derrière Caddy avec SQLite persistant.

### Traduction automatique

La langue utilisée par l’enseignant lors de la création devient la langue
d’origine du quiz. Les anciens quiz sans langue enregistrée sont considérés
comme français.

La traduction :

- démarre uniquement à la demande de l’élève ;
- couvre le titre, les questions et les réponses, mais jamais le code ;
- peut être désactivée à tout moment pour retrouver le texte original ;
- s’exécute localement avec l’API `Translator` du navigateur.

Le navigateur peut télécharger un modèle de langue lors de la première
utilisation. Aucun service de traduction externe n’est configuré par Open Quiz.
Si le navigateur ou la paire de langues n’est pas compatible, le quiz reste
inchangé. Consultez la
[documentation Chrome](https://developer.chrome.com/docs/ai/translator-api) et
la [compatibilité MDN](https://developer.mozilla.org/docs/Web/API/Translator).

## ⚙️ Configuration

Les secrets sont stockés dans `open-quiz-backend/.env`, ignoré par Git. Les
fichiers d’exemple ne contiennent aucune vraie donnée sensible.

### Paramètres essentiels

| Variable | Description | Valeur locale |
| --- | --- | --- |
| `DATABASE_URL` | URL SQLAlchemy de la base | `sqlite:///./open-quiz.db` |
| `JWT_SECRET` | Signature des jetons, 32 caractères minimum | obligatoire |
| `TOTP_ENCRYPTION_KEY` | Chiffrement TOTP, distinct du secret JWT | obligatoire |
| `ADMIN_USERNAME` | Identifiant administrateur, 80 caractères maximum | `admin` |
| `ADMIN_PASSWORD` | Mot de passe administrateur, 16 à 256 caractères | obligatoire |
| `FRONTEND_ORIGIN` | Origine HTTP(S) exacte, sans `/` final | `http://localhost:5173` |
| `APP_ENV` | `development`, `test` ou `production` | `development` |

Le frontend accepte aussi `VITE_API_URL`. Laissez-la vide avec le proxy Vite
ou le déploiement Caddy fourni. Utilisez une URL absolue uniquement si l’API
est servie séparément, avec une configuration CORS correspondante. Pour Docker,
transmettez cette même origine avec `--build-arg VITE_API_URL=https://api.example.com`
afin que la politique CSP Caddy autorise les requêtes API.

<details>
<summary><strong>Durées, limites de débit et conservation</strong></summary>

| Variable | Description | Défaut |
| --- | --- | --- |
| `ACCESS_TOKEN_MINUTES` | Durée d’un jeton d’accès, de 1 à 30 min | `15` |
| `REFRESH_TOKEN_DAYS` | Durée maximale d’une session, de 1 à 30 jours | `7` |
| `LOGIN_ATTEMPTS` | Connexions admises par fenêtre | `5` |
| `LOGIN_WINDOW_SECONDS` | Fenêtre de limitation des connexions | `900` |
| `QUIZ_JOIN_ATTEMPTS` | Tentatives pour rejoindre un quiz | `20` |
| `QUIZ_PARTICIPANT_ATTEMPTS` | Requêtes d’un participant par fenêtre | `240` |
| `QUIZ_VIOLATION_ATTEMPTS` | Alertes de surveillance par fenêtre | `20` |
| `QUIZ_RATE_WINDOW_SECONDS` | Fenêtre des limites publiques | `60` |
| `QUIZ_RESULT_RETENTION_DAYS` | Conservation des résultats terminés | `365` |
| `PROBLEM_REPORT_ATTEMPTS` | Signalements admis par fenêtre (instance entière) | `30` |
| `PROBLEM_REPORT_WINDOW_SECONDS` | Fenêtre de limitation des signalements | `900` |
| `PROBLEM_REPORT_RETENTION_DAYS` | Conservation maximale des signalements | `90` |
| `MAX_REQUEST_BODY_BYTES` | Taille des requêtes ordinaires | `65536` |

</details>

<details>
<summary><strong>Informations légales et publiques de l’instance</strong></summary>

Les pages `/legal-notice`, `/privacy`, `/accessibility` et `/cookie-settings`
chargent ces informations depuis l’API. Une valeur absente ne bloque pas le
démarrage, mais affiche un avertissement public.

| Variable | Information à faire valider |
| --- | --- |
| `LEGAL_HOST_NAME` | Nom ou raison sociale de l’hébergeur |
| `LEGAL_HOST_ADDRESS` | Adresse de l’hébergeur |
| `PRIVACY_CONTROLLER_NAME` | Responsable du traitement |
| `PRIVACY_CONTROLLER_CONTACT` | Contact pour l’exercice des droits |
| `PRIVACY_DPO_CONTACT` | Contact du DPO compétent |
| `PRIVACY_LEGAL_BASIS` | Base légale validée avec le DPO |
| `PRIVACY_RECIPIENTS` | Destinataires et sous-traitants autorisés |
| `PRIVACY_TEACHER_DATA_RETENTION` | Conservation des comptes enseignants |
| `PRIVACY_STUDENT_DATA_RETENTION` | Conservation des données élèves |
| `PRIVACY_SECURITY_LOG_RETENTION` | Conservation des journaux de sécurité |
| `ACCESSIBILITY_CONTACT` | Contact pour une alternative accessible |
| `ACCESSIBILITY_SCHEME_URL` | URL du schéma pluriannuel d’accessibilité |
| `ACCESSIBILITY_ACTION_PLAN_URL` | URL du plan d’action annuel |

Le modèle fourni suit le régime de l’édition non professionnelle anonyme. Les
contacts RGPD et accessibilité doivent être institutionnels ou fonctionnels,
jamais personnels.

Conservez la mention « Accessibilité : non conforme » tant qu’aucun audit RGAA
complet et valide n’a été réalisé. Des tests automatisés ne remplacent pas cet
audit.

Dans l’Éducation nationale, l’hébergement ne vaut pas homologation. Consultez
le DPO, inscrivez le traitement au registre, documentez sa base légale,
encadrez les sous-traitants et informez les élèves et représentants légaux.

Références :
[traitements éducatifs](https://eduscol.education.fr/4920/interfaces-entre-les-applications-nationales-et-les-solutions-numeriques-tierces-pour-l-education),
[DPO de l’Éducation nationale](https://eduscol.education.fr/4935/delegues-la-protection-des-donnees-dpd),
[RGAA 4.1.2](https://accessibilite.numerique.gouv.fr/) et
[cookies et traceurs](https://www.cnil.fr/fr/cookies-et-autres-traceurs/que-dit-la-loi).

</details>

## 🏗️ Architecture

| Partie | Technologies |
| --- | --- |
| API | Python 3.14, FastAPI, SQLAlchemy, SQLite |
| Interface | React 19, TypeScript, Vite, Tailwind CSS |
| Sécurité | JWT, cookies HttpOnly, TOTP, Argon2, Fernet |
| Python navigateur | Pyodide dans un Web Worker |
| Production | Docker Compose et Caddy |
| Qualité | pytest, Ruff, ESLint, Prettier, TypeScript |

```text
Navigateur
  ├─ espace élève
  ├─ espace enseignant
  └─ espace administrateur
          │ HTTPS / JSON
          ▼
Caddy (SPA, CSP, fichiers statiques, proxy /api)
          │ réseau Docker interne
          ▼
FastAPI (authentification, métier, limites de débit)
          │
          ▼
SQLite en mode WAL (volume persistant)
```

Le backend applique les autorisations, effectue les tirages, fige le barème de
chaque session, calcule les notes et limite le débit. Le frontend conserve les
jetons d’accès enseignant en mémoire. Les cookies de session enseignant sont
HttpOnly et rotatifs ; les jetons d’authentification et de participation élève
restent dans `sessionStorage` le temps de l’onglet.

### Structure du dépôt

```text
.
├── .github/                 CI, Dependabot et modèles de contribution
├── open-quiz-backend/
│   ├── app/                 configuration, modèles, sécurité et routes API
│   ├── scripts/             récupération 2FA et rotation des secrets
│   └── tests/               tests API, sécurité et migrations SQLite
├── open-quiz-frontend/
│   ├── public/locales/      huit catalogues de traduction
│   ├── public/pyodide/      runtime Python hors ligne
│   ├── scripts/             validations frontend
│   └── src/                 API cliente, pages et composants React
├── CHANGELOG.md             nouveautés et changements incompatibles
├── docker-compose.yml       déploiement autonome
├── update.ps1               mise à jour Windows
└── update.sh                mise à jour Unix
```

## ✅ Tests et qualité

### Backend

```shell
cd open-quiz-backend
uv run ruff check app tests main.py scripts
uv run ruff format --check app tests main.py scripts
uv run pytest -q
```

Appliquez le formatage avec `uv run ruff format app tests main.py scripts`.

### Frontend

```shell
cd open-quiz-frontend
pnpm lint
pnpm format:check
pnpm test
pnpm typecheck
pnpm test:e2e
pnpm build
pnpm audit --audit-level low
```

`pnpm test` vérifie notamment les huit catalogues de traduction et leurs
variables d’interpolation. `pnpm format` applique Prettier.

## 📦 Déploiement

### Compiler le frontend localement

```shell
cd open-quiz-frontend
pnpm build
pnpm preview
```

La compilation écrit les fichiers dans `open-quiz-frontend/dist`.

### Déployer avec Docker

1. Copiez `open-quiz-backend/.env.production.example` vers
   `open-quiz-backend/.env`.
2. Configurez l’origine HTTPS et les trois secrets robustes.
3. Sauvegardez `TOTP_ENCRYPTION_KEY` dans un gestionnaire de secrets.
4. Validez et démarrez les conteneurs.

```shell
docker compose config --quiet
docker compose up --detach --build --remove-orphans --wait
docker compose ps
```

Le frontend écoute uniquement sur `127.0.0.1:7800`. Publiez-le derrière un
reverse proxy HTTPS :

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Vérifiez ensuite l’état de l’API :

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est `{"status":"ok"}`. Appliquez les mises à jour en
avance rapide avec `update.ps1` sous Windows ou `sh ./update.sh` sous Unix.

## 💾 Exploitation et sauvegardes

### Migration de 0.1.x vers 0.2.0

Effectuez une sauvegarde de la base avant le premier démarrage en `0.2.0`. La
migration SQLite est automatique, mais elle comporte volontairement des
changements incompatibles avec l’ancien fonctionnement :

- les anciens élèves dépourvus de compte sont supprimés ;
- les répartitions de quiz en pourcentages sont converties en nombres de
  questions par difficulté ;
- le barème historique d’une question est reporté sur ses bonnes réponses lors
  de la migration vers la notation réponse par réponse.

Les nouvelles sessions utilisent des instantanés du tirage, de l’ordre et du
réglage des points négatifs afin qu’une modification ultérieure du quiz ne
change pas leurs notes.

- surveillez `/api/health`, l’espace disque et le certificat TLS ;
- sauvegardez régulièrement le volume `open-quiz-data` avec un outil compatible
  SQLite WAL, ou pendant un arrêt contrôlé ;
- conservez `TOTP_ENCRYPTION_KEY` : sa perte impose une nouvelle inscription
  TOTP pour chaque compte ;
- centralisez les événements JSON `security.*`, `auth.login_rate_limited` et
  `auth.refresh_reuse_detected` ;
- testez une restauration avant de considérer une sauvegarde comme valide.

## 🛠️ Dépannage

| Problème | Solution |
| --- | --- |
| L’API refuse de démarrer | Vérifiez les secrets, `APP_ENV` et l’absence de `/` final dans `FRONTEND_ORIGIN`. |
| Le navigateur bloque l’API | Faites correspondre exactement l’origine visible et `FRONTEND_ORIGIN`. |
| Un enseignant a perdu son authentificateur | Utilisez « Récupérer l’accès », `uv run python -m scripts.reset_two_factor identifiant` ou, en Docker, `docker compose exec open-quiz-backend python -m scripts.reset_two_factor identifiant`. |
| Le frontend ne trouve pas le backend | Démarrez l’API sur le port 8000 ou configurez `VITE_API_URL`. |
| La traduction est indisponible | Utilisez un navigateur et une paire de langues compatibles avec `Translator`. |
| Docker ne devient pas sain | Consultez `docker compose ps`, puis `docker compose logs open-quiz-backend open-quiz-frontend`. |

## 🤝 Contribution, sécurité et licence

Lisez [CONTRIBUTING.md](CONTRIBUTING.md) avant de proposer un changement.

Ne publiez jamais une vulnérabilité dans une issue. Utilisez la procédure
privée décrite dans [SECURITY.md](SECURITY.md).

Open Quiz est distribué sous [licence MIT](LICENSE).

## 🙏 Remerciements

Le projet s’appuie notamment sur FastAPI, React, Pyodide, Caddy et les nombreux
projets libres référencés dans les fichiers de verrouillage.
