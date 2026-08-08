# Open Quiz Backend

## Technologies utilisées

- Python 3.14 ou supérieur
- FastAPI avec ses dépendances standard
- SQLAlchemy avec SQLite
- Authentification JWT et mots de passe hachés avec Argon2
- uv pour la gestion de l'environnement, des dépendances et du verrouillage des versions

## Démarrage

Prérequis : Python 3.14 et `uv`.

Copiez `.env.example` vers `.env`, puis renseignez deux secrets aléatoires
distincts d'au moins 32 caractères pour les jetons JWT et le chiffrement TOTP,
ainsi qu'un mot de passe administrateur robuste. Le compte administrateur est
créé au premier démarrage. Son identifiant interne est ensuite enregistré comme
état de sécurité : modifier `ADMIN_USERNAME` renomme ce même compte au lieu de
créer un second administrateur. Ses droits, son état et son mot de passe restent
synchronisés avec `.env`.

Sous Linux et macOS, protégez le fichier avant le premier démarrage avec
`chmod 600 .env`. L'application réapplique cette permission à `.env` ainsi
qu'aux fichiers SQLite locaux à chaque démarrage.

```shell
uv sync
uv run fastapi dev main.py
```

La documentation interactive est disponible sur `http://localhost:8000/docs`.

## Vérifications

```shell
uv run ruff check .
uv run ruff format --check app tests main.py scripts
uv run pytest -q
```

La suite teste les parcours d’administration et d’enseignement, la participation
des élèves, la notation, la migration du schéma SQLite, les limites de débit et
la rotation des sessions d’authentification.

## Modèle fonctionnel 0.2

- les enseignants créent des comptes élèves indépendamment des classes, puis
  affectent chaque compte à une classe ;
- les élèves s’authentifient sur `/api/student-auth/login` avant de rejoindre un
  examen avec son code ;
- les quiz `exam` sont notés et lancés par l’enseignant, tandis que les banques
  d’entraînement sont autorisées par classe puis tirées et démarrées librement
  par l’élève ;
- chaque proposition porte son propre nombre de points. Un quiz choisit si les
  points négatifs sont appliqués ou ramenés à zéro lors de la correction ;
- les questions sont tirées individuellement au lancement pour chaque élève ;
- le tirage, l’ordre et le réglage des points négatifs sont enregistrés dans la
  session pour préserver la notation historique.

Chaque quiz conserve dans `source_language` la langue d’interface utilisée lors
de sa création. Cette valeur est renvoyée dans les réponses destinées à l’élève
afin que le frontend puisse proposer une traduction lorsque sa propre langue
diffère. Le backend ne traduit aucun contenu et ne transmet aucune question à
un service de traduction. Lors de la migration d’une base SQLite existante, les
anciens quiz reçoivent la valeur par défaut `fr`.

Le point `/api/health` vérifie à la fois le processus HTTP et l’accès réel à la
base de données. Il doit être utilisé pour les contrôles de disponibilité.

Les jetons d’accès enseignant et administrateur expirent rapidement et restent
uniquement en mémoire dans le navigateur. Leurs sessions longues utilisent un
cookie HttpOnly rotatif et révocable. Chaque appareil reste reconnu pendant
7 jours au maximum à partir de la dernière validation 2FA, sans prolongation
glissante lors de l’utilisation. Après cette échéance, ou sur un nouvel
appareil, une nouvelle validation 2FA est obligatoire. La réutilisation d’un
ancien jeton révoque toute sa famille de sessions.

Les comptes élèves n’utilisent pas TOTP ni le cookie de renouvellement. Ils
reçoivent après vérification du mot de passe un jeton Bearer de 12 heures,
invalidé par un changement de mot de passe ou de `JWT_SECRET`. Les jetons de
participation à un quiz restent distincts et limités à leur session.

Un changement de mot de passe administrateur révoque ses sessions et invalide
immédiatement ses jetons d’accès. Un changement de `JWT_SECRET` révoque toutes
les sessions. Les enseignants et administrateurs doivent configurer une
application d’authentification TOTP lors de leur première connexion. Les secrets
TOTP sont chiffrés dans SQLite avec `TOTP_ENCRYPTION_KEY`. Sauvegardez cette
clé : si elle est perdue ou remplacée, chaque enseignant et administrateur devra
réinitialiser son inscription 2FA.

Les mots de passe élèves restent hachés pour l’authentification. Une copie
récupérable est chiffrée avec `STUDENT_CREDENTIAL_ENCRYPTION_KEY` afin que seul
le professeur propriétaire puisse les consulter ou les exporter. Les comptes
créés avant cette fonctionnalité nécessitent une réinitialisation de mot de
passe avant que celui-ci puisse être affiché.

Si un utilisateur perd son authentificateur, réinitialisez son inscription 2FA
et révoquez ses sessions actives depuis l'espace d'administration en utilisant
« Récupérer l'accès ». Cette action définit un nouveau mot de passe, révoque les
sessions et impose une nouvelle inscription 2FA. L'outil de secours en ligne de
commande reste disponible avec :

```shell
uv run python -m scripts.reset_two_factor identifiant
```

Pour renouveler le secret JWT et le mot de passe administrateur locaux sans les
afficher dans le terminal, tout en révoquant immédiatement les sessions
existantes :

```shell
uv run python scripts/rotate_local_secrets.py
```

`APP_ENV` est obligatoire. En production, utilisez `APP_ENV=production` et une
origine frontend HTTPS exacte.
Les cookies deviennent alors automatiquement sécurisés, la documentation
interactive est désactivée et les requêtes HTTP sont redirigées vers HTTPS.

La limitation d'authentification réserve chaque tentative atomiquement en base
de données avant le calcul Argon2 ou la vérification TOTP et fonctionne donc
avec plusieurs processus. `LOGIN_ATTEMPTS` limite les tentatives par nom
d'utilisateur normalisé, sans dépendre de l'adresse IP transmise par le reverse
proxy. Configurez tout de même le reverse proxy comme seule entrée vers le
backend et n'acceptez les en-têtes `Forwarded` que de ce proxy. Le conteneur
fourni respecte cette contrainte grâce au réseau Docker interne.

`MAX_REQUEST_BODY_BYTES` limite la taille des requêtes applicatives. Le
conteneur Uvicorn ajoute également une limite de concurrence et des délais de
connexion courts. Conservez des limites équivalentes sur le reverse proxy
externe.

Les résultats terminés sont supprimés automatiquement lorsqu'un professeur
consulte ses résultats et qu'ils dépassent `QUIZ_RESULT_RETENTION_DAYS`
(365 jours par défaut). Un professeur peut aussi supprimer immédiatement un
résultat depuis son tableau de bord. Cette suppression efface la session, les
participants, les réponses et les alertes associées.

SQLite est configuré en mode WAL avec vérification des clés étrangères, attente
sur verrou et contrôle de disponibilité. Le volume `/data` doit rester
persistant et être sauvegardé avec un outil compatible SQLite WAL ou pendant un
arrêt contrôlé.

Lors du premier démarrage en `0.2.0`, la migration supprime les anciens élèves
sans compte et convertit les répartitions en pourcentages vers des quantités par
difficulté. Une migration ultérieure reporte le barème historique de chaque
question sur ses bonnes réponses. Sauvegardez la base avant toute migration.

Les images de questions sont décodées, limitées en dimensions puis réencodées
avant stockage. Les métadonnées et les trames d'animation ne sont pas
conservées. Une image destinée à un élève n’est accessible qu’avec son jeton de
participation, pour sa question courante et pendant que la session est
effectivement en cours.

Les événements de sécurité sont émis en JSON sur la sortie standard avec un
horodatage UTC. En production, envoyez-les vers un collecteur central en
écriture seule pour l'application, avec contrôle d'accès, alertes et politique
de rétention. Alertez notamment sur `auth.refresh_reuse_detected`,
`auth.login_rate_limited` et les événements `security.*`.

Les limitations de débit utilisent uniquement des sujets bornés connus du
serveur (compte, session, participant ou quota global). Une adresse IP peut
figurer dans un événement d’audit, mais elle n’est jamais une clé de limitation.

Les alertes de surveillance d’un quiz sont des déclarations du navigateur de
l’élève. Elles aident un enseignant à interpréter une session, mais elles ne
sont ni exhaustives ni résistantes à la falsification et ne doivent jamais
servir seules à une sanction ou à une décision automatique.

Le fichier `docker-compose.yml` situé à la racine du dépôt démarre le backend
sur un réseau interne, conserve SQLite dans un volume dédié et fait passer
`/api` par Caddy. L'origine publique configurée dans `FRONTEND_ORIGIN` doit
correspondre exactement à l'adresse utilisée par le navigateur.
