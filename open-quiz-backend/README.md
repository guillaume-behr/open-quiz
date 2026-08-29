# API Open Quiz

Backend FastAPI d’Open Quiz. Il centralise l’authentification, les autorisations,
les tirages de questions, la notation, les sessions temps réel et la persistance
PostgreSQL.

Consultez aussi le [README principal](../README.md), le
[guide de déploiement](../docs/deployment.md) et le
[guide de contribution](../CONTRIBUTING.md).

## Installation avec Docker

Le backend fait partie de l’installation Docker Compose d’Open Quiz, qui
configure également PostgreSQL et le frontend. Depuis la racine du dépôt,
suivez la [procédure d’installation recommandée](../README.md#installation) :

```shell
sh ./install.sh
```

Le lancement direct avec Python décrit plus bas est réservé au développement.

## Technologies

- Python 3.14 et uv ;
- FastAPI et Uvicorn ;
- SQLAlchemy avec PostgreSQL et Psycopg ;
- Argon2, JWT, TOTP et Fernet pour les mécanismes d’authentification ;
- pytest, Ruff et pip-audit pour la qualité et la sécurité.

## Développement local

Cette procédure lance uniquement l’API en mode développement. Elle ne remplace
pas l’installation Docker Compose recommandée pour utiliser une instance.

### Prérequis

- Python 3.14 ou supérieur ;
- [uv](https://docs.astral.sh/uv/) ;
- PostgreSQL 17, par exemple le service `open-quiz-database` de Docker Compose.

Depuis la racine du dépôt, créez la configuration locale et démarrez PostgreSQL :

```shell
sh ./install-dev.sh
```

Le script génère automatiquement :

- `JWT_SECRET` ;
- `TOTP_ENCRYPTION_KEY` ;
- `STUDENT_CREDENTIAL_ENCRYPTION_KEY` ;
- `ADMIN_PASSWORD` ;
- `POSTGRES_PASSWORD`.

Les trois secrets cryptographiques sont distincts et suffisamment longs. Le
script protège `open-quiz-backend/.env`, affiche les identifiants administrateur
une seule fois et conserve une configuration de développement existante et
compatible sans l’écraser. Après le démarrage, il vérifie une connexion
PostgreSQL authentifiée afin de détecter un ancien volume utilisant un autre
mot de passe.

Installez les dépendances et démarrez l’API :

```shell
cd open-quiz-backend
uv sync
uv run fastapi dev main.py
```

L’API répond sur `http://localhost:8000`. En développement, les interfaces
OpenAPI sont disponibles sur :

- Swagger UI : `http://localhost:8000/docs` ;
- ReDoc : `http://localhost:8000/redoc` ;
- schéma JSON : `http://localhost:8000/openapi.json`.

Ces trois routes sont désactivées en production.

## Configuration

Les valeurs sont chargées depuis `.env`. Ce fichier est protégé en mode `0600`
sur les systèmes POSIX.

### Variables principales

| Variable                            | Requise | Défaut                       | Contraintes principales                  |
| ----------------------------------- | ------- | ---------------------------- | ---------------------------------------- |
| `DATABASE_URL`                      | oui     | —                            | URL PostgreSQL SQLAlchemy                |
| `POSTGRES_PASSWORD`                 | oui     | —                            | mot de passe PostgreSQL                  |
| `JWT_SECRET`                        | oui     | —                            | au moins 32 caractères                   |
| `TOTP_ENCRYPTION_KEY`               | oui     | —                            | distincte de `JWT_SECRET`, 32 caractères |
| `STUDENT_CREDENTIAL_ENCRYPTION_KEY` | oui     | —                            | distincte des deux autres, 32 caractères |
| `ADMIN_USERNAME`                    | oui     | `admin` dans l’exemple       | 1 à 80 caractères                        |
| `ADMIN_PASSWORD`                    | oui     | —                            | 16 à 256 caractères                      |
| `FRONTEND_ORIGIN`                   | non     | `http://localhost:5173`      | origine exacte sans chemin ni `/` final  |
| `APP_ENV`                           | oui     | `development` dans l’exemple | `development`, `test` ou `production`    |

En production, `FRONTEND_ORIGIN` doit utiliser HTTPS. Le compte administrateur
est créé au premier démarrage, puis reste synchronisé avec `ADMIN_USERNAME` et
`ADMIN_PASSWORD`. Un changement de mot de passe révoque ses sessions actives.

### Sessions, limites et conservation

| Variable                        | Défaut  | Valeurs acceptées |
| ------------------------------- | ------- | ----------------- |
| `ACCESS_TOKEN_MINUTES`          | `15`    | 1 à 30            |
| `REFRESH_TOKEN_DAYS`            | `7`     | 1 à 30            |
| `LOGIN_ATTEMPTS`                | `5`     | 3 à 20            |
| `LOGIN_WINDOW_SECONDS`          | `900`   | 60 minimum        |
| `GLOBAL_LOGIN_ATTEMPTS`         | `500`   | 50 à 100 000      |
| `GLOBAL_LOGIN_WINDOW_SECONDS`   | `60`    | 10 à 3 600        |
| `QUIZ_JOIN_ATTEMPTS`            | `20`    | 5 à 100           |
| `QUIZ_PARTICIPANT_ATTEMPTS`     | `240`   | 30 à 1 000        |
| `QUIZ_VIOLATION_ATTEMPTS`       | `20`    | 5 à 100           |
| `QUIZ_RATE_WINDOW_SECONDS`      | `60`    | 10 à 3 600        |
| `QUIZ_RESULT_RETENTION_DAYS`    | `365`   | 1 à 3 650 jours   |
| `PROBLEM_REPORT_ATTEMPTS`       | `30`    | 1 à 1 000         |
| `PROBLEM_REPORT_WINDOW_SECONDS` | `900`   | 60 à 86 400       |
| `PROBLEM_REPORT_RETENTION_DAYS` | `90`    | 1 à 365 jours     |
| `MAX_REQUEST_BODY_BYTES`        | `65536` | 1 024 à 1 048 576 |

Le modèle de production réduit volontairement
`PROBLEM_REPORT_ATTEMPTS` à `5`. Ce quota concerne toute l’instance et évite
d’utiliser l’adresse IP comme identifiant de limitation.

`MAX_REQUEST_BODY_BYTES` s’applique aux requêtes ordinaires. Après
authentification d’un enseignant, la création, la modification et l’import de
questions acceptent jusqu’à 96 Mio afin de transporter les images encodées. Un
import peut contenir jusqu’à 64 Mio d’images décodées et chaque image jusqu’à
20 Mio. Un reverse proxy placé devant l’API doit conserver une exception
équivalente pour ces routes.

Les variables légales et d’accessibilité sont décrites dans le
[guide de déploiement](../docs/deployment.md#renseigner-les-informations-publiques).

## Vue d’ensemble de l’API

La documentation OpenAPI locale reste la source la plus précise pour les
schémas de requête et de réponse.

| Préfixe                   | Responsabilité                                               |
| ------------------------- | ------------------------------------------------------------ |
| `/api/health`             | disponibilité du processus et de la base                     |
| `/api/public-information` | informations légales publiques de l’instance                 |
| `/api/auth`               | connexion, TOTP et renouvellement des comptes privilégiés    |
| `/api/student-auth`       | connexion et session des élèves                              |
| `/api/admin`              | administration des comptes enseignants                       |
| `/api/users`              | profil et opérations sur le compte courant                   |
| `/api/students`           | comptes élèves et export des identifiants                    |
| `/api/classes`            | classes, affectations et import groupé                       |
| `/api/grade-levels`       | niveaux utilisés par les classes et banques                  |
| `/api/question-banks`     | banques, questions, images et import/export                  |
| `/api/quizzes`            | examens, entraînements, rattrapages et résultats             |
| `/api/problem-reports`    | création publique et gestion administrative des signalements |

### Authentification

| Contexte                     | Mécanisme                                                 |
| ---------------------------- | --------------------------------------------------------- |
| Enseignant ou administrateur | `Authorization: Bearer <access-token>`                    |
| Élève                        | `Authorization: Bearer <student-access-token>`            |
| Participation à un quiz      | en-tête `X-Quiz-Token` après l’inscription à la session   |
| Renouvellement privilégié    | cookie HttpOnly et en-tête `X-Refresh-Proof`              |
| WebSocket temps réel         | premier message JSON `{ "token": "..." }` sous 5 secondes |

Les jetons d’accès enseignant et administrateur sont courts. Leur session
longue utilise un cookie HttpOnly rotatif et une nouvelle validation TOTP est
requise au plus tard après sept jours par défaut, ou sur un nouvel appareil.
Les jetons élève expirent après 12 heures et n’utilisent ni TOTP ni cookie de
renouvellement.

### Pagination

Les collections paginées acceptent `page` et `page_size`. La taille vaut 8 par
défaut et 100 au maximum. Les réponses exposent :

- `X-Page` ;
- `X-Page-Size` ;
- `X-Total-Count`.

### Mises à jour temps réel

Les routes `/api/quizzes/live/*` diffusent les changements de sessions aux
enseignants et aux élèves. L’origine WebSocket est validée, le premier message
authentifie la connexion et le serveur vérifie régulièrement que le jeton reste
valide.

Le bus temps réel est conservé en mémoire. Le conteneur utilise donc un seul
worker Uvicorn. N’activez pas plusieurs workers sans remplacer ce bus par un
mécanisme partagé et tester le comportement en charge.

## Modèle fonctionnel

- l’administrateur crée et gère les comptes enseignants ;
- chaque enseignant possède ses comptes élèves, ses classes et ses banques ;
- un compte élève existe indépendamment de son affectation à une classe ;
- les examens sont lancés par l’enseignant, tandis que les entraînements sont
  démarrés librement par l’élève depuis les banques autorisées ;
- les rattrapages permettent de repasser une sélection d’examens déjà effectués ;
- un examen peut partager le même tirage entre tous les élèves ou attribuer un
  tirage individuel à chacun ;
- chaque proposition porte son propre nombre de points et le quiz décide si les
  valeurs négatives sont appliquées ; sans points négatifs, sélectionner aussi
  une proposition incorrecte annule les points de la question ;
- une banque d’entraînement utilisée par un examen actif devient indisponible
  pour la classe jusqu’à la fin ou l’annulation de cet examen ;
- les questions rédactionnelles restent en attente d’une correction manuelle ;
- les questions, leur ordre et le barème sont figés dans la session pour
  préserver les résultats historiques.

Les notes publiées sont verrouillées. Les alertes de surveillance envoyées par
le navigateur sont informatives, non exhaustives et falsifiables ; elles ne
doivent jamais déclencher seules une sanction ou une décision automatique.

## Imports et exports

### Classes et élèves

`GET /api/classes/example` télécharge un exemple adapté aux niveaux configurés.
`POST /api/classes/import` valide puis crée les classes, comptes élèves et
affectations dans une transaction unique. Une erreur de structure, un niveau
inconnu, un doublon ou un conflit annule tout l’import.

Exemple minimal :

```json
{
    "classes": [
        {
            "name": "TG1",
            "grade_level": "Tle",
            "students": [
                {
                    "identifier": "martin.l",
                    "display_name": "Lucas Martin"
                }
            ]
        }
    ]
}
```

Les mots de passe générés sont hachés pour l’authentification et chiffrés pour
rester imprimables par l’enseignant propriétaire.

### Banques de questions

- `GET /api/question-banks/example` fournit le format JSON versionné ;
- `GET /api/question-banks/{id}/export` exporte une banque complète ;
- `POST /api/question-banks/import` importe atomiquement une banque et ses
  questions.

Les images JPEG, PNG, WebP et GIF sont décodées, contrôlées puis réencodées
avant stockage. Les métadonnées et les trames d’animation ne sont pas
conservées. Une image destinée à un élève n’est accessible qu’avec le jeton de
sa participation et pendant une session valide.

## Stockage et conservation

Docker Compose exécute PostgreSQL dans `open-quiz-database` et conserve ses
données dans le volume `open-quiz-postgres-data`. Le backend accepte uniquement
une URL PostgreSQL et crée le schéma courant dans une base vide au démarrage.
Il n’existe pas de reprise depuis les anciennes bases : le passage à cette
version nécessite un nouveau volume PostgreSQL.

La purge des résultats et signalements expirés s’exécute au démarrage puis
toutes les heures. Un enseignant peut aussi supprimer immédiatement un résultat
et toutes ses participations, réponses et alertes associées.

Pour une procédure de sauvegarde et restauration PostgreSQL, consultez le
[guide d’exploitation](../docs/deployment.md#sauvegarder-les-données).

## Sécurité et exploitation

- tous les mots de passe sont hachés avec Argon2 ;
- les secrets TOTP et les copies récupérables des mots de passe élèves sont
  chiffrés avec deux clés distinctes ;
- les changements de mot de passe et de secret JWT révoquent les sessions
  concernées ;
- les routes sensibles utilisent des limites de débit persistées en base ;
- les événements d’audit sont écrits en JSON sur la sortie d’erreur standard ;
- les réponses API ne sont pas mises en cache et reçoivent des en-têtes de
  sécurité ;
- en production, l’API force HTTPS et désactive OpenAPI.

Le conteneur limite Uvicorn à 1 024 connexions concurrentes, mais ce nombre
n’est pas une garantie de capacité. Dimensionnez et testez l’instance selon la
machine, la taille des classes, les images et le trafic attendu.

## Scripts d’administration

### Réinitialiser le TOTP d’un compte

Cette commande révoque les sessions et impose une nouvelle inscription TOTP :

```shell
uv run python -m scripts.reset_two_factor identifiant
```

Dans Docker :

```shell
docker compose exec open-quiz-backend \
    /app/.venv/bin/python -m scripts.reset_two_factor identifiant
```

Privilégiez toutefois l’action **Récupérer l’accès** dans l’espace
administrateur : elle remplace également le mot de passe du compte ciblé.

### Renouveler les secrets locaux

Pour remplacer `JWT_SECRET` et `ADMIN_PASSWORD` sans les afficher :

```shell
uv run python scripts/rotate_local_secrets.py
```

Le script révoque les sessions longues et crée dans le répertoire backend une
sauvegarde `.env.env.<horodatage>.bak` contenant les anciens secrets. Cette
sauvegarde n’est pas ignorée par Git : déplacez-la immédiatement vers un espace
protégé ou supprimez-la dès qu’elle n’est plus utile. Redémarrez ensuite l’API
pour charger les nouvelles valeurs.

Ce script vise uniquement un environnement de développement local. Avec
l’installation Docker Compose, modifiez le fichier `.env` de l’hôte, protégez
l’ancienne copie puis recréez le service.

## Vérifications

Les tests ont besoin du rôle et de la base `open_quiz_test`, créés par
`sh ./install-dev.sh` depuis la racine du dépôt. Définissez `TEST_DATABASE_URL`
pour viser un autre serveur PostgreSQL.

Installez les dépendances de développement puis reproduisez les contrôles CI :

```shell
uv sync --frozen --dev
uv run --frozen ruff check app tests main.py scripts
uv run --frozen ruff check --select S app main.py scripts
uv run --frozen ruff format --check app tests main.py scripts
uv run --frozen pytest -q
uv run --frozen pip-audit
```

Appliquez le formatage avec :

```shell
uv run ruff format app tests main.py scripts
```

Avant de contribuer, consultez [CONTRIBUTING.md](../CONTRIBUTING.md). Signalez
les vulnérabilités selon [SECURITY.md](../SECURITY.md), jamais dans une issue
publique. Open Quiz est distribué sous [licence MIT](../LICENSE).
