# Architecture d’Open Quiz

Vue d’ensemble d’un déploiement Docker Compose. Le
[guide de déploiement](deployment.md) décrit son exploitation.

## Services

| Service              | Rôle                                                                                                                            | Réseaux                       |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| `open-quiz-frontend` | Caddy : sert l’interface compilée et relaie `/api/*` (WebSocket compris) vers l’API ; seul service publié, sur `127.0.0.1:7800` | `open-quiz-edge`, `open-quiz` |
| `open-quiz-backend`  | API FastAPI servie par Uvicorn (`OPEN_QUIZ_API_WORKERS` processus) ; applique les migrations Alembic au démarrage               | `open-quiz`                   |
| `open-quiz-database` | PostgreSQL ; seule source d’état de l’application                                                                               | `open-quiz`                   |

Le réseau `open-quiz` est interne : ni l’API ni la base n’atteignent Internet,
et rien ne les atteint sans passer par le frontend. `open-quiz-edge` ne relie
que le frontend au reverse proxy HTTPS de la machine.

## Où vit l’état

- **PostgreSQL** (volume `open-quiz-postgres-data`) : comptes, contenus,
  sessions, résultats, jetons de rafraîchissement, et aussi les compteurs des
  limites de débit, partagés ainsi entre tous les workers.
- **Événements en direct** : chaque worker garde les WebSocket de ses propres
  clients ; une modification faite par un worker est relayée aux autres par
  `NOTIFY`/`LISTEN` PostgreSQL (`app/live/relay.py`). Aucun état n’est partagé
  en mémoire entre workers, et aucun service supplémentaire (Redis…) n’est
  nécessaire.
- **Fichiers `.env`** : `open-quiz-backend/.env` (secrets de l’API, dont les
  clés qui chiffrent les secrets TOTP et les mots de passe élèves),
  `open-quiz-backend/.env.database` (mot de passe du superutilisateur
  PostgreSQL) et `.env` à la racine (réglages Docker Compose).
- **Navigateur** : l’exécution du code Python des questions (Pyodide) et la
  traduction ont lieu chez l’utilisateur, sans état côté serveur.

L’API se connecte avec le rôle `open_quiz_app`, sans privilège de
superutilisateur ; `scripts/database-roles.sql` le crée.

## Organisation du code de l’API

Le paquet `open-quiz-backend/app` est découpé en couches. Chacune n’importe
que les couches situées au-dessous d’elle ; `tests/test_layers.py` le vérifie.

| Couche (de bas en haut)                      | Contenu                                                                                                    |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `core/`, `models.py`, `enums.py`, `schemas/` | configuration, base de données, sécurité, middleware, limites de débit ; tables ; corps des requêtes       |
| `domain/`, `live/`                           | règles pures sans accès à la base (images, libellés, jetons de choix) ; diffusion temps réel entre workers |
| `records/`                                   | lecture et écriture des lignes : recherches, contrôles de propriété, créations                             |
| `services/`                                  | opérations métier : réponses, notation, tirages, cycle de vie des sessions, maintenance                    |
| `responses/`                                 | corps des réponses envoyées aux enseignants et aux élèves                                                  |
| `routers/`                                   | routes HTTP et WebSocket, regroupées par ressource (`quizzes/`, `question_banks/`, `classes/`)             |
| `application.py`                             | assemblage de l’application : routes, middleware et tâches de fond                                         |

`app/data/` contient les fichiers fournis avec l’API, comme l’exemple de
banque de questions téléchargeable. Les tests de `tests/` sont rangés par
domaine ; leurs aides communes se trouvent dans `tests/support.py`.
