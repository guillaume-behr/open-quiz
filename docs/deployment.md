# Déployer et exploiter Open Quiz

Ce guide complète le [README principal](../README.md). Il s’adresse aux
personnes qui administrent une instance Open Quiz avec Docker Compose.

> [!IMPORTANT]
> Open Quiz est encore en préversion. Son schéma de données et ses interfaces
> peuvent évoluer : sauvegardez la base et les secrets avant chaque mise à jour,
> puis lisez les notes de la release visée.

## 📖 Sommaire

- [Préparer l’instance](#-préparer-linstance)
- [Démarrer les services](#-démarrer-les-services)
- [Publier l’application en HTTPS](#-publier-lapplication-en-https)
- [Vérifier et surveiller l’instance](#-vérifier-et-surveiller-linstance)
- [Sauvegarder les données](#-sauvegarder-les-données)
- [Mettre à jour Open Quiz](#-mettre-à-jour-open-quiz)
- [Gérer les secrets et les accès](#-gérer-les-secrets-et-les-accès)
- [Configurer la conservation et les limites](#-configurer-la-conservation-et-les-limites)
- [Configurer les mentions RGPD et légales](#-configurer-les-mentions-rgpd-et-légales)
- [Répondre à une demande d’effacement](#-répondre-à-une-demande-deffacement)
- [Dépannage](#-dépannage)

## 🧱 Préparer l’instance

### Prérequis

- Docker Engine avec un plugin Compose prenant en charge
  `docker compose up --wait` ;
- Git et un shell compatible POSIX (Linux, macOS ou WSL sous Windows) ;
- un nom de domaine valide et un reverse proxy HTTPS ;
- une stratégie de sauvegarde hors de la machine qui héberge l’application.

Clonez le dépôt, puis lancez l’installation guidée depuis sa racine :

```shell
git clone https://github.com/guillaume-behr/open-quiz.git
cd open-quiz
sh ./install.sh
```

Le script demande le nom de domaine public, par exemple `quiz.example.com`.
Saisissez-le sans `https://`, chemin ni `/` final. Il effectue ensuite toutes
les opérations nécessaires au premier démarrage :

1. il génère localement des valeurs aléatoires distinctes pour PostgreSQL (le
   superutilisateur et le rôle de l’API), JWT, TOTP et le chiffrement des
   identifiants élèves ;
2. il génère le mot de passe du compte administrateur ;
3. il définit l’origine du frontend en HTTPS et reprend tous les autres réglages
   de production depuis le fichier d’exemple ;
4. il crée `open-quiz-backend/.env` et `open-quiz-backend/.env.database` avec
   des permissions réservées au propriétaire, ainsi que le fichier `.env` de
   la racine (réglages de Docker Compose) depuis `.env.example`, s’il n’existe
   pas encore ;
5. il lance `update.sh --no-pull`, qui démarre la base, crée le rôle
   PostgreSQL de l’API, construit les images, démarre les services et attend
   leur état sain. Le clone est déjà à jour, donc aucune
   révision n’est récupérée à cette étape.

Pour une installation automatisée, le domaine peut être fourni en argument
plutôt que saisi au clavier :

```shell
sh ./install.sh --domain quiz.example.com
```

Enregistrez immédiatement le mot de passe administrateur affiché par le script :
il ne sera pas réaffiché. L’installation refuse d’écraser un fichier `.env`
existant afin de ne pas remplacer des secrets ou rendre des données chiffrées
illisibles.

Le script ne modifie ni le DNS, ni le pare-feu, ni la configuration TLS ou le
reverse proxy de l’hôte. Configurez ces éléments séparément dans la section
[Publier l’application en HTTPS](#-publier-lapplication-en-https).

### Secrets obligatoires

Les secrets vivent dans deux fichiers que Git ignore, générés par `install.sh`
au premier démarrage : vous n’avez rien à écrire vous-même.

- `open-quiz-backend/.env` est lu par l’API seule ;
- `open-quiz-backend/.env.database` est lu par le conteneur PostgreSQL seul et
  ne contient que `POSTGRES_PASSWORD`, le mot de passe du superutilisateur
  `open_quiz`.

L’API ne se connecte pas en superutilisateur, mais avec son propre rôle,
`open_quiz_app`, propriétaire de la base et de ses tables, sans aucun privilège
d’administration de PostgreSQL. `update.sh` crée ce rôle et l’ajuste à chaque
passage ([`scripts/database-roles.sql`](../scripts/database-roles.sql)). Ainsi,
une injection SQL ne permettrait ni de lire les fichiers du serveur ni
d’exécuter un programme, et une base compromise ne livre ni `JWT_SECRET` ni la
clé des identifiants élèves. Le superutilisateur ne sert qu’aux sauvegardes,
aux restaurations et à ce script, par le socket local du conteneur.

| Variable                              | Rôle                                               | Exigence                                              |
| ------------------------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| `DATABASE_URL`                        | accès à la base depuis l’API                       | URL PostgreSQL SQLAlchemy, rôle `open_quiz_app`       |
| `DATABASE_PASSWORD`                   | mot de passe du rôle `open_quiz_app`               | 16 caractères au moins : lettres, chiffres, `. _ ~ -` |
| `POSTGRES_PASSWORD` (`.env.database`) | mot de passe du superutilisateur PostgreSQL        | valeur aléatoire robuste                              |
| `JWT_SECRET`                          | signature des jetons de session                    | 32 caractères aléatoires au moins                     |
| `TOTP_ENCRYPTION_KEY`                 | chiffrement des secrets de double authentification | 32 caractères, distincts du secret JWT                |
| `STUDENT_CREDENTIAL_ENCRYPTION_KEY`   | chiffrement des mots de passe élèves relisibles    | 32 caractères, distincts des deux autres              |
| `ADMIN_PASSWORD`                      | mot de passe du compte administrateur              | 16 à 256 caractères, différent des secrets            |

Les trois clés doivent être distinctes les unes des autres : l’API refuse de
démarrer si deux d’entre elles coïncident, ou si l’une a gardé sa valeur
d’exemple.

> [!CAUTION]
> Conservez `.env` et `.env.database` dans une sauvegarde chiffrée. Ne placez jamais ses valeurs
> dans Git, dans une issue, ni dans les journaux d’exploitation.

### Réglages non secrets

Ces variables se modifient à tout moment. Relancez `sh ./update.sh` ensuite, et
mettez aussi à jour le reverse proxy lorsque le domaine change.

| Variable          | Rôle                                      | Valeur attendue                         |
| ----------------- | ----------------------------------------- | --------------------------------------- |
| `ADMIN_USERNAME`  | identifiant du compte administrateur      | 1 à 80 caractères                       |
| `FRONTEND_ORIGIN` | origine exacte visible dans le navigateur | HTTPS, sans chemin ni `/` final         |
| `APP_ENV`         | mode d’exécution                          | `production` pour une instance publique |

Le compte administrateur est créé au premier démarrage. Ensuite,
`ADMIN_USERNAME` et `ADMIN_PASSWORD` continuent de piloter ce même compte : une
modification du mot de passe révoque ses sessions actives.

Les fichiers [`.env.example`](../open-quiz-backend/.env.example) et
[`.env.production.example`](../open-quiz-backend/.env.production.example)
listent toutes les variables disponibles, y compris celles décrites plus loin
dans [la conservation et les limites](#-configurer-la-conservation-et-les-limites)
et dans [les mentions RGPD](#-configurer-les-mentions-rgpd-et-légales).

## ▶️ Démarrer les services

Le premier démarrage est effectué automatiquement par `install.sh` via
`update.sh`. Pour contrôler le résultat :

```shell
docker compose config --quiet
docker compose ps
```

Le déploiement crée trois services :

- `open-quiz-frontend`, qui sert l’application et transmet `/api` au backend ;
- `open-quiz-backend`, qui exécute l’API ;
- `open-quiz-database`, qui exécute PostgreSQL et stocke ses données dans le
  volume persistant `open-quiz-postgres-data`.

Le backend n’est pas publié sur l’hôte. Le frontend écoute uniquement sur
`127.0.0.1:7800` afin qu’un reverse proxy soit le seul point d’entrée public.

### Plusieurs workers

Le backend démarre un seul processus Uvicorn par défaut. Pour en lancer
davantage, définissez `OPEN_QUIZ_API_WORKERS` dans le fichier `.env` de la
racine du dépôt, à côté de `docker-compose.yml` (distinct de
`open-quiz-backend/.env`), puis relancez `sh ./update.sh`. Ce fichier, créé
par `install.sh`, contient les réglages de Docker Compose ; `.env.example`
les liste tous avec leur valeur par défaut. Ne les passez jamais dans la
ligne de commande : la mise à jour suivante ne les verrait pas, et `update.sh`
le signale.

```shell
OPEN_QUIZ_API_WORKERS=2
```

Les mises à jour en direct atteignent les élèves et enseignants connectés à
n’importe quel worker : chaque publication est relayée aux autres processus par
PostgreSQL. Mesuré sur 4 cœurs avec PostgreSQL local, ce relais réveille les
35 WebSockets d’une session tenues par un autre worker en 1,8 ms en médiane
(2,6 ms au 95ᵉ centile), et 250 WebSockets en 8 ms. Le script
`python -m scripts.live_relay_benchmark` refait cette mesure sur une instance.

Chaque worker ouvre jusqu’à 15 connexions PostgreSQL pour les requêtes
(`DATABASE_POOL_SIZE` + `DATABASE_MAX_OVERFLOW`, dans
`open-quiz-backend/.env`), 5 pour les limites de débit et 2 pour le relais,
soit 22 en tout. Restez sous `max_connections` (100 par défaut) : au-delà de
4 workers, augmentez-le ou réduisez leur nombre.

Le conteneur du backend est aussi limité en nombre de processus, threads
compris : 256 par défaut. Chaque worker peut utiliser une centaine de threads
(40 pour les requêtes, jusqu’à 32 pour les tâches de fond, plus quelques
autres). Comptez environ `100 × workers + 64` et, à partir de 2 workers,
augmentez la limite dans le même fichier `.env` racine :

```shell
OPEN_QUIZ_API_WORKERS=3
OPEN_QUIZ_API_PIDS=384
```

### Mémoire des conteneurs

Le backend est limité à 2 Go de mémoire et le frontend à 512 Mo, sans swap :
une rafale d’imports d’images ou de tentatives de connexion ne peut ainsi pas
priver PostgreSQL et l’hôte de mémoire. Le backend ne décode par ailleurs que
deux images et ne calcule que quatre condensats de mots de passe à la fois ;
les demandes suivantes attendent leur tour. Une image qui attend plus de
30 secondes répond 503 (`SERVER_BUSY`), et les imports de classes laissent
toujours un condensat libre pour les connexions.

Avec plusieurs workers, ou si des imports volumineux échouent faute de
mémoire, ajustez ces limites dans le même fichier `.env` racine :

```shell
OPEN_QUIZ_API_MEMORY=4g
OPEN_QUIZ_PROXY_MEMORY=512m
```

La base de données n’a volontairement aucune limite, ni de mémoire ni de
processus : l’interrompre en plein travail coûterait plus cher que la mémoire
qu’elle prend, et PostgreSQL lance un processus par connexion, si bien qu’une
limite refuserait des connexions avant d’atteindre `max_connections`.

### Changer le sous-réseau interne

Les trois services communiquent sur le réseau interne `open-quiz`, en
`172.28.0.0/24` par défaut. Le backend ne fait confiance aux en-têtes
`X-Forwarded-*` que s’ils viennent de l’adresse du frontend sur ce réseau :
c’est ce qui lui permet de reconnaître une requête arrivée en HTTPS.

Si ce sous-réseau entre en conflit avec un réseau de l’établissement,
définissez `OPEN_QUIZ_SUBNET_PREFIX` dans le fichier `.env` de la racine du
dépôt, à côté de `docker-compose.yml` (distinct de `open-quiz-backend/.env`) :

```shell
OPEN_QUIZ_SUBNET_PREFIX=10.42.0
```

Le sous-réseau devient `10.42.0.0/24`. Les adresses des services et le proxy
de confiance du backend suivent automatiquement. Docker ne modifie pas le
sous-réseau d’un réseau existant : arrêtez d’abord les services, puis relancez
la mise à jour.

```shell
docker compose down
sh ./update.sh
```

`docker compose down` conserve le volume de la base de données.

## 🔒 Publier l’application en HTTPS

Placez un reverse proxy HTTPS devant `127.0.0.1:7800`. Exemple Caddy :

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Pour Nginx, adaptez puis installez
l'[exemple de serveur virtuel](nginx.conf). Il inclut la
redirection HTTPS, les en-têtes transmis à l'application et la limite nécessaire
aux imports de questions. Il transmet également la négociation de protocole
nécessaire aux connexions WebSocket. Conservez `proxy_http_version 1.1` et les
en-têtes `Upgrade` et `Connection`. La valeur explicite de `Connection` évite de
dépendre d’un bloc `map` au niveau `http`, qui n’est pas accepté dans tous les
emplacements d’inclusion d’un virtual host. L’en-tête `Origin`, validé par
l’application, et les en-têtes `Sec-WebSocket-*` sont transmis automatiquement
par Nginx et ne doivent pas être réécrits.

Nginx remplace aussi `X-Forwarded-For` par l’adresse du client directement
connecté, au lieu d’accepter une chaîne fournie par celui-ci. Le Caddy du
conteneur n’accepte les chaînes transférées que depuis les plages privées du
réseau Docker, complète les en-têtes `X-Forwarded-*` puis les transmet à
FastAPI. Ne remplacez pas `$remote_addr` par `$proxy_add_x_forwarded_for` lorsque
Nginx est le point d’entrée public direct. Si un CDN ou un autre load balancer
précède Nginx, configurez explicitement ses plages de confiance au lieu de
reprendre cette règle telle quelle.

L’exemple Nginx limite enfin, par adresse IP, le rythme des connexions aux
comptes (`limit_req`) et le nombre de connexions simultanées (`limit_conn`).
Open Quiz ne le fait volontairement pas lui-même, pour ne conserver aucune
adresse : ses propres limites portent sur les comptes et sur l’instance
entière. Le reverse proxy est donc le seul endroit où borner ce qu’une adresse
peut envoyer. Un établissement partage souvent une seule adresse publique : les
valeurs fournies laissent une classe entière se connecter en même temps ;
ajustez-les à la taille de l’établissement. Avec Caddy, le module
[`caddy-ratelimit`](https://github.com/mholt/caddy-ratelimit) joue ce rôle.

Le nom de domaine doit correspondre exactement à `FRONTEND_ORIGIN`. En
production, l’API redirige les requêtes qu’elle considère comme HTTP ; conservez
donc les en-têtes de protocole transmis par les reverse proxies.

L’API refuse aussi, par une réponse 400, toute requête dont l’en-tête `Host`
n’est ni le nom de `FRONTEND_ORIGIN` ni un nom interne du déploiement : le
reverse proxy doit donc transmettre le nom demandé par le navigateur
(`proxy_set_header Host $host` pour Nginx ; Caddy le fait par défaut). Si
l’instance répond aussi sous un autre nom, ajoutez-le à
`open-quiz-backend/.env` :

```shell
TRUSTED_HOSTS=api.example.com
```

L’interface et l’API partagent toujours la même origine : le conteneur
frontend transmet `/api` au backend, qui n’est publié nulle part ailleurs. Une
API servie sur une autre origine n’est pas prise en charge par
`docker-compose.yml`. Conservez `FRONTEND_ORIGIN` égal à l’origine visible dans
le navigateur, par exemple `https://quiz.example.com`.

Si le reverse proxy externe limite la taille des requêtes, prévoyez jusqu’à
96 Mio pour les routes authentifiées de création, modification et import de
questions. Les requêtes ordinaires restent limitées par
`MAX_REQUEST_BODY_BYTES`.

### Moteurs de recherche

L’instance demande aux moteurs de recherche de ne pas l’indexer : le fichier
`/robots.txt` interdit toute exploration et chaque page porte l’en-tête
`X-Robots-Tag: noindex`. Pour autoriser l’indexation, modifiez
`open-quiz-frontend/public/robots.txt` et retirez cet en-tête du `Caddyfile`,
puis relancez `sh ./update.sh`.

## 🩺 Vérifier et surveiller l’instance

Le contrôle de disponibilité vérifie le processus HTTP et l’accès à la base :

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est :

```json
{ "status": "ok" }
```

Commandes utiles :

```shell
docker compose ps
docker compose logs --tail 200 open-quiz-database open-quiz-backend open-quiz-frontend
docker compose logs --follow open-quiz-database open-quiz-backend open-quiz-frontend
```

Surveillez au minimum :

- la disponibilité de `/api/health` ;
- l’espace disque du volume Docker et de l’emplacement des sauvegardes ;
- la validité du certificat TLS ;
- les redémarrages ou états `unhealthy` des conteneurs ;
- les événements JSON `security.*`, `auth.login_rate_limited` et
  `auth.refresh_reuse_detected` ;
- l’événement `auth.global_budget_floor_used`, émis lorsque le budget
  d’authentification de l’instance est épuisé et qu’un compte connu est tout de
  même servi. Isolé, il ne signale rien ; répété, il indique que quelqu’un
  sature les connexions et que seuls les comptes déjà existants passent encore.

Les journaux peuvent contenir des informations d’audit. Centralisez-les dans un
espace à accès restreint et appliquez la durée de conservation validée pour
votre instance.

### Journal des requêtes

Le backend écrit une ligne JSON par requête sur sa sortie standard, sans
adresse IP ni identifiant : la route figure sous sa forme paramétrée, jamais
avec un code de session ou un numéro.

```json
{
    "event": "http.request",
    "method": "GET",
    "route": "/api/quizzes/sessions/{session_id}",
    "status": 200,
    "duration_ms": 12.4
}
```

Le journal d’accès d’Uvicorn, qui contiendrait l’adresse des clients, est
désactivé.

## 💾 Sauvegarder les données

Une sauvegarde exploitable comprend :

1. une sauvegarde logique cohérente de la base PostgreSQL ;
2. une copie protégée de `open-quiz-backend/.env`, de
   `open-quiz-backend/.env.database` et du fichier `.env` de la racine ;
3. la version ou le commit Open Quiz correspondant.

`TOTP_ENCRYPTION_KEY` et `STUDENT_CREDENTIAL_ENCRYPTION_KEY` ne sont pas
stockées dans la base. Sans le fichier `.env` correspondant, une restauration
de la base reste incomplète.

`open-quiz-backend/.env` contient aussi `ADMIN_PASSWORD` en clair : cette
valeur continue de définir le mot de passe du compte administrateur. Protégez
ce fichier et chacune de ses copies comme le mot de passe lui-même.

### Sauvegarder avec `backup.sh`

```shell
sh ./backup.sh
```

Le script écrit une sauvegarde `pg_dump` au format personnalisé, cohérente sans
arrêter l’application, dans `backups/open-quiz-AAAA-MM-JJTHHMMSSZ.dump`. Il la
relit avec `pg_restore --list` avant de la conserver. Le dossier `backups/` est
ignoré par Git, lisible par son seul propriétaire, et chaque fichier est en
`0600` : une sauvegarde contient les données personnelles des élèves. À côté,
un fichier `.meta` note la révision d’Open Quiz, la révision du schéma et une
empreinte non réversible des clés de chiffrement de `open-quiz-backend/.env`,
jamais les clés elles-mêmes.

Seules les 14 sauvegardes les plus récentes du dossier sont conservées : les
plus anciennes sont supprimées, ainsi les données effacées d’un élève ne
survivent pas indéfiniment dans `backups/` et le disque ne se remplit pas.
Réglez ce nombre avec `OPEN_QUIZ_BACKUP_KEEP` dans le fichier `.env` de la
racine, ou pour une exécution avec `--keep N`. `--directory` choisit un autre
dossier. Pour une sauvegarde quotidienne, ajoutez une ligne à la crontab de
l’utilisateur du déploiement :

```shell
30 2 * * * cd /srv/open-quiz && sh ./backup.sh >>backups/backup.log 2>&1
```

`update.sh` sauvegarde aussi la base avant chaque mise à jour, sauf avec
`--no-backup` ou lorsque la base ne tourne pas encore, et `restore.sh` avant
chaque restauration ; la même limite s’applique à ces sauvegardes.

`install.sh`, `update.sh`, `backup.sh` et `restore.sh` ne s’exécutent jamais
en même temps : chacun prend un verrou (`.open-quiz.lock`) et échoue
immédiatement si un autre le tient, ce qu’une tâche planifiée signale. Un
verrou laissé par un processus disparu est repris automatiquement.

Copiez ensuite les sauvegardes vers un stockage distinct et protégé, et testez
régulièrement une restauration dans une instance isolée.

Une sauvegarde n’est pas chiffrée. Les secrets TOTP et les mots de passe élèves
qu’elle contient le sont, mais par des clés rangées dans
`open-quiz-backend/.env` : copier ce fichier au même endroit que les
sauvegardes revient à les livrer en clair à qui les trouve. Conservez donc les
deux séparément — le `.env` dans un gestionnaire de secrets ou un coffre, les
sauvegardes ailleurs — ou chiffrez les sauvegardes avant de les sortir de
l’hôte, par exemple avec [age](https://age-encryption.org/) :

```shell
age --recipient age1… --output sauvegarde.dump.age backups/open-quiz-2026-10-29T180000Z.dump
```

`restore.sh` attend le fichier déchiffré.

### Restaurer avec `restore.sh`

```shell
sh ./restore.sh backups/open-quiz-2026-10-29T180000Z.dump
```

Le script vérifie que le fichier est une sauvegarde lisible et, si son fichier
`.meta` est présent, que les clés de chiffrement de `open-quiz-backend/.env`
sont celles de la sauvegarde : sinon, les secrets TOTP et les mots de passe
élèves restaurés seraient illisibles, et il refuse de continuer sans
`--force-key-mismatch`. Il demande ensuite de taper `restore` ; `--yes` permet
de s’en passer dans un script. Rien n’est modifié avant cette confirmation. Il
sauvegarde d’abord les données actuelles dans `backups/`, arrête l’API et
l’interface, puis restaure la sauvegarde en une seule transaction : en cas
d’échec, la base reste dans son état précédent. La base devient exactement la
sauvegarde : une table qu’elle ne contient pas, comme celle d’une migration
plus récente, disparaît, et l’API migre au démarrage une sauvegarde prise par
une version antérieure. Le script rend ensuite au rôle `open_quiz_app` les
objets restaurés, puis redémarre les conteneurs.

Utilisez le fichier `.env` correspondant à la sauvegarde, puis vérifiez
`/api/health`, les connexions et un échantillon de résultats. Une restauration
en production suit le même principe uniquement après validation complète sur
une instance isolée.

> [!CAUTION]
> Une restauration remplace les données actuelles. Arrêtez les écritures,
> conservez une copie supplémentaire de l’état présent et validez la procédure
> sur une instance de test avant toute restauration en production.

## ⬆️ Mettre à jour Open Quiz

Avant une mise à jour :

1. lisez les notes de la release visée (`CHANGELOG.md`) ;
2. sauvegardez le fichier `.env` ; `update.sh` sauvegarde la base ;
3. vérifiez que le dépôt ne contient aucune modification locale à préserver.

Pour installer une release précise, ce qui est recommandé en production :

```shell
sh ./update.sh --version v1.0.0
```

Sans `--version`, le script suit la branche du clone (`git pull --ff-only`) :
il déploie alors la dernière révision, y compris les changements non publiés
de la section `[Unreleased]` du `CHANGELOG.md`, et le signale.

```shell
sh ./update.sh
```

Après `--version` ou un retour arrière, le clone n’est plus sur une branche :
la mise à jour suivante se fait avec `--version`, ou bien revenez d’abord sur
la branche avec `git checkout master`.

Le script vérifie d’abord que Docker est accessible, que
`open-quiz-backend/.env` existe et que le dépôt ne contient aucune modification
locale, puis récupère la révision demandée. Il affiche la révision avant et
après la mise à jour. Il valide ensuite la configuration Compose, sauvegarde la
base dans `backups/` (désactivable avec `--no-backup`), et note dans
`backups/*.rollback` ce qu’un retour arrière demande : la révision en service,
cette sauvegarde et les images en service, conservées sous le nom
`open-quiz-rollback` (les trois dernières par service). Il démarre ensuite la
base, crée ou ajuste le rôle `open_quiz_app`, reconstruit les conteneurs,
attend leur état sain (120 s par défaut, réglable avec `--wait-timeout` ou
`OPEN_QUIZ_WAIT_TIMEOUT`) et affiche leur statut ainsi que l’origine publique
configurée.

### Revenir à la version précédente

Si la mise à jour échoue, ou si la nouvelle version pose problème :

```shell
sh ./update.sh --rollback
```

Après confirmation, le script remet le code de la révision précédente, ses
images (sans rien reconstruire), puis la base sauvegardée juste avant la mise à
jour, et redémarre l’ensemble. Tout ce qui a été écrit depuis la mise à jour est
perdu. Sans sauvegarde (`--no-backup`), seuls le code et les images reviennent.
En cas d’échec, `update.sh` affiche cette commande.

`sh ./restore.sh` seul ne suffit pas : il ne remplace que la base, et le
backend de la nouvelle version, redémarré ensuite, réappliquerait aussitôt ses
migrations.

Pour reconstruire et redémarrer sans récupérer de révision, par exemple après
avoir modifié `.env` :

```shell
sh ./update.sh --no-pull
```

Au démarrage, le backend applique lui-même les migrations du schéma en
attente, dans une seule transaction : en cas d’échec, la base reste dans son
état précédent et le backend redémarre sans devenir sain. Une base créée par la
version 0.4.0 ou antérieure est reprise automatiquement, sans perte de
données. Pour connaître la révision d’une base :

```shell
docker compose exec open-quiz-backend /app/.venv/bin/alembic current
```

Après la mise à jour, vérifiez `docker compose ps`, `/api/health`, la connexion
des trois rôles et les journaux du backend.

### Changer de version majeure de PostgreSQL

Une nouvelle version majeure de PostgreSQL (17 → 18 par exemple) ne sait pas
ouvrir le dossier de données d’une version précédente : changer la seule
ligne `image:` empêcherait la base de démarrer. Dependabot ne propose donc
jamais ce changement ; il se fait par sauvegarde et restauration. La CI
exécute cette procédure à chaque modification, de PostgreSQL 16 vers la
version épinglée, puis le retour en arrière.

1. Sauvegardez la base, puis copiez la sauvegarde hors de l’hôte avec les
   fichiers `.env` (voir [Sauvegarder les données](#-sauvegarder-les-données)) :

    ```shell
    sh ./backup.sh
    ```

2. Arrêtez les services :

    ```shell
    docker compose down
    ```

3. Dans `docker-compose.yml`, remplacez l’étiquette et l’empreinte de l’image
   `postgres:` par celles de la nouvelle version. Notez l’ancienne ligne pour
   un éventuel retour. Dans un fork qui garde la CI, faites le même changement
   dans `.github/workflows/ci.yml` : la CI vérifie que les deux concordent.

4. Mettez l’ancien dossier de données de côté, sans le supprimer : copiez le
   volume dans un volume de réserve, puis retirez l’original pour que Docker
   Compose en crée un vide. Remplacez `ANCIENNE_IMAGE` par l’ancienne image,
   par exemple `postgres:17.11-alpine3.24` :

    ```shell
    volume=$(docker volume ls --quiet --filter label=com.docker.compose.volume=open-quiz-postgres-data)
    docker volume create "$volume-old"
    docker run --rm --volume "$volume:/from:ro" --volume "$volume-old:/to" ANCIENNE_IMAGE cp -a /from/. /to/
    docker volume rm "$volume"
    ```

5. Démarrez la nouvelle base, qui recrée son superutilisateur à partir de
   `open-quiz-backend/.env.database`, puis restaurez la sauvegarde.
   `restore.sh` recrée aussi le rôle `open_quiz_app` de l’API et lui rend les
   objets restaurés, comme `install.sh` :

    ```shell
    docker compose up --wait --detach open-quiz-database
    sh ./restore.sh backups/open-quiz-AAAA-MM-JJTHHMMSSZ.dump
    ```

6. Vérifiez l’instance :
    - `docker compose exec open-quiz-database psql --username=open_quiz --command="SHOW server_version"`
      indique la nouvelle version ;
    - `/api/health` répond `{"status":"ok"}` ;
    - l’administrateur et un enseignant se connectent, un examen et ses
      résultats s’affichent ;
    - le nombre de lignes des principales tables (`users`, `quizzes`,
      `quiz_results`…) est celui d’avant la mise à jour.

    En cas de problème, revenez à l’ancienne version : arrêtez les services,
    remettez l’ancienne ligne `image:`, puis replacez l’ancien dossier de
    données dans le volume avant de redémarrer :

    ```shell
    docker compose down
    docker volume rm "$volume"
    docker compose create open-quiz-database
    docker run --rm --volume "$volume-old:/from:ro" --volume "$volume:/to" ANCIENNE_IMAGE cp -a /from/. /to/
    docker compose up --wait --detach
    ```

7. Gardez le volume de réserve tant que la nouvelle version n’a pas fonctionné
   quelques jours, sauvegardes quotidiennes comprises, puis supprimez-le : il
   contient les données personnelles des élèves telles qu’au jour de la mise à
   jour.

    ```shell
    docker volume rm "$volume-old"
    ```

## 🔑 Gérer les secrets et les accès

### Effet d’une rotation

| Élément                             | Effet d’un changement                                                             |
| ----------------------------------- | --------------------------------------------------------------------------------- |
| `JWT_SECRET`                        | invalide les jetons d’accès et révoque les sessions longues au prochain démarrage |
| `ADMIN_PASSWORD`                    | remplace le mot de passe administrateur et révoque ses sessions                   |
| `TOTP_ENCRYPTION_KEY`               | réinscription TOTP de tous les comptes privilégiés ; sessions conservées          |
| `STUDENT_CREDENTIAL_ENCRYPTION_KEY` | rend les mots de passe élèves déjà enregistrés irrécupérables                     |

Conservez les deux clés de chiffrement tant que les données associées doivent
rester utilisables. Pour une rotation en production, modifiez le fichier
`.env`, reconstruisez ou redémarrez les services, puis vérifiez les journaux.

### Récupérer un compte ayant perdu son TOTP

Privilégiez l’action **Récupérer l’accès** dans l’espace administrateur. Elle
change le mot de passe, révoque les sessions et impose une nouvelle inscription
TOTP.

La commande de secours réinitialise uniquement l’inscription TOTP et révoque
les sessions du compte :

```shell
docker compose exec open-quiz-backend \
    /app/.venv/bin/python -m scripts.reset_two_factor identifiant
```

La commande demande une confirmation. Ajoutez `--yes` uniquement dans une
procédure automatisée qui a déjà validé l’identifiant ciblé.

## ⏳ Configurer la conservation et les limites

Les valeurs ci-dessous sont fournies dans les fichiers `.env` d’exemple.

| Variable                           | Rôle                                                    | Défaut                                          |
| ---------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| `ACCESS_TOKEN_MINUTES`             | durée des jetons d’accès privilégiés                    | `15`                                            |
| `REFRESH_TOKEN_DAYS`               | durée maximale d’une session longue                     | `7`                                             |
| `STUDENT_ACCESS_TOKEN_HOURS`       | durée des sessions élève (2 à 12)                       | `2`                                             |
| `LOGIN_ATTEMPTS`                   | tentatives par compte et par fenêtre                    | `10`                                            |
| `LOGIN_WINDOW_SECONDS`             | fenêtre des tentatives par compte                       | `900`                                           |
| `TWO_FACTOR_DAILY_ATTEMPTS`        | codes de double authentification par compte et par jour | `30`                                            |
| `TWO_FACTOR_BROWSER_TRUST`         | dispense du code un navigateur validé le jour même      | `true`                                          |
| `GLOBAL_LOGIN_ATTEMPTS`            | tentatives de connexion pour toute l’instance           | `2000`                                          |
| `GLOBAL_LOGIN_WINDOW_SECONDS`      | fenêtre du quota global                                 | `60`                                            |
| `QUIZ_JOIN_ATTEMPTS`               | tentatives pour rejoindre une session                   | `60`                                            |
| `QUIZ_PARTICIPANT_ATTEMPTS`        | requêtes d’un participant par fenêtre                   | `900`                                           |
| `QUIZ_VIOLATION_ATTEMPTS`          | alertes de surveillance par fenêtre                     | `60`                                            |
| `QUIZ_RATE_WINDOW_SECONDS`         | fenêtre des limites liées aux quiz                      | `60`                                            |
| `QUIZ_RESULT_RETENTION_DAYS`       | conservation des résultats terminés                     | `365`                                           |
| `TRAINING_RESULT_RETENTION_DAYS`   | conservation des entraînements terminés                 | `365`                                           |
| `ABANDONED_SESSION_RETENTION_DAYS` | délai avant de solder une session jamais clôturée       | `7`                                             |
| `CLASS_IMPORT_ATTEMPTS`            | imports de classes par fenêtre et par enseignant        | `30`                                            |
| `CLASS_IMPORT_WINDOW_SECONDS`      | fenêtre du quota d’imports de classes                   | `900`                                           |
| `PROBLEM_REPORT_ATTEMPTS`          | signalements anonymes par fenêtre pour toute l’instance | `60` en local, `5` dans l’exemple de production |
| `PROBLEM_REPORT_WINDOW_SECONDS`    | fenêtre du quota de signalements                        | `900`                                           |
| `PROBLEM_REPORT_RETENTION_DAYS`    | conservation des signalements                           | `90`                                            |
| `MAX_REQUEST_BODY_BYTES`           | taille des requêtes applicatives ordinaires             | `65536`                                         |
| `DATABASE_POOL_SIZE`               | connexions PostgreSQL gardées ouvertes par worker       | `5`                                             |
| `DATABASE_MAX_OVERFLOW`            | connexions supplémentaires par worker sous charge       | `10`                                            |
| `DATABASE_POOL_TIMEOUT_SECONDS`    | attente d’une connexion libre avant de répondre 503     | `10`                                            |

Les codes de double authentification sont limités deux fois : par
`LOGIN_ATTEMPTS` sur `LOGIN_WINDOW_SECONDS`, et par
`TWO_FACTOR_DAILY_ATTEMPTS` sur 24 heures. Une connexion réussie ne remet pas
ce second compteur à zéro ; **Récupérer l’accès** et la commande de secours le
font.

Après une double authentification réussie, le navigateur reçoit le cookie
`open_quiz_two_factor_trust`. Jusqu’à minuit, heure de l’appareil, et 24 heures
au plus, le mot de passe suffit pour se reconnecter depuis ce navigateur. Un
changement de mot de passe, une nouvelle inscription TOTP, la désactivation du
compte ou une rotation de `JWT_SECRET` y mettent fin, tout comme le bouton de
`/cookie-settings`. Une simple déconnexion le conserve : sur un poste partagé,
effacez les données de l’appareil ou passez `TWO_FACTOR_BROWSER_TRUST` à
`false`.

La suppression des données expirées est appliquée au démarrage, puis toutes les
heures. Adaptez ces valeurs à la politique validée pour votre instance avant de
collecter des données réelles.

Une session en cours se termine d’elle-même à l’échéance de son minuteur, mais
une salle d’attente jamais lancée ou une session laissée en pause reste active
jusqu’à ce que son enseignant la clôture. Passé
`ABANDONED_SESSION_RETENTION_DAYS`, la maintenance s’en charge à sa place : un examen qui a recueilli des réponses est noté puis conservé au
titre de `QUIZ_RESULT_RETENTION_DAYS`, tandis qu’une salle d’attente sans
réponse et les entraînements interrompus sont supprimés. Un enseignant
désactivé ou parti ne laisse donc plus de données sans terme.

`MAX_REQUEST_BODY_BYTES` ne couvre pas les routes authentifiées de création,
modification et import de questions : elles disposent d’une limite de 96 Mio
pour transporter les images encodées.

Les images des questions et des choix sont rangées dans la table
`stored_images`, une seule fois par contenu identique : importer deux fois une banque ne
recopie pas ses images, et lister des questions n’en lit aucune. La maintenance
horaire supprime les questions retirées de leur banque qu’aucune session ne
conserve plus, puis les images qu’aucune question n’utilise plus. Une passe de
maintenance qui échoue est journalisée et reprise à l’heure suivante.

## 🛡️ Configurer les mentions RGPD et légales

Les pages publiques `/legal-notice`, `/privacy`, `/accessibility` et
`/cookie-settings` n’embarquent aucun texte propre à votre établissement :
elles lisent ces variables via `/api/public-information`. Une valeur absente ne
bloque pas le démarrage, mais s’affiche en rouge sur la page sous la mention
« Non renseigné », et l’instance publie alors une politique sans responsable
identifiable.

Renseignez-les dans `open-quiz-backend/.env`, puis redémarrez l’API. En
production, les mentions obligatoires laissées vides sont énumérées au
démarrage dans les journaux, sous l’événement
`security.public_information_incomplete`. Le contact du DPO, le contact
d’accessibilité et les deux URL d’accessibilité en sont exclus : ils restent
facultatifs pour le logiciel, pas nécessairement pour vous.

### Responsable du traitement et droits

Ce bloc porte les mentions exigées par les articles 13 et 14 du RGPD. Sans lui,
une personne concernée n’a aucune adresse à qui écrire pour exercer ses droits.

- **`PRIVACY_CONTROLLER_NAME`** — l’entité qui décide du traitement :
  établissement, collectivité ou académie, jamais une personne physique.
  Exemple : `Collège Jean-Moulin`.
- **`PRIVACY_CONTROLLER_CONTACT`** — l’adresse où envoyer une demande d’accès,
  de rectification ou d’effacement. Exemple : `rgpd@college-jean-moulin.fr`.
- **`PRIVACY_DPO_CONTACT`** — le délégué à la protection des données compétent,
  distinct du responsable. Exemple : `dpo@ac-exemple.fr`.
- **`PRIVACY_LEGAL_BASIS`** — la base légale retenue, en toutes lettres. Dans
  l’enseignement public, c’est une mission d’intérêt public et non le
  consentement. Exemple : `Mission d’intérêt public (article 6.1.e)`.
- **`PRIVACY_RECIPIENTS`** — qui accède aux données, hébergeur et prestataires
  techniques compris. Exemple : `Enseignants de l’établissement et hébergeur`.

> [!IMPORTANT]
> Si vous inscrivez le consentement comme base légale, la page ajoute
> d’elle-même la portabilité et le droit de retrait. Vérifiez que ce fondement
> est réellement celui de votre traitement : pour une autorité publique, il ne
> l’est généralement pas.

### Durées de conservation

Quatre durées sont réellement appliquées par la purge et publiées
automatiquement sur `/privacy`. Trois autres sont du texte libre : elles
décrivent ce que le logiciel ne peut pas appliquer seul, et c’est à vous de
les tenir.

| Variable                         | Ce qu’elle fait                           |
| -------------------------------- | ----------------------------------------- |
| `QUIZ_RESULT_RETENTION_DAYS`     | supprime les résultats d’examens terminés |
| `TRAINING_RESULT_RETENTION_DAYS` | supprime les entraînements terminés       |
| `PROBLEM_REPORT_RETENTION_DAYS`  | supprime les signalements                 |
| `REFRESH_TOKEN_DAYS`             | borne le cookie d’authentification        |

Les trois variables en texte libre :

- **`PRIVACY_TEACHER_DATA_RETENTION`** — la durée de vie d’un compte
  enseignant, que vous appliquez en le supprimant depuis l’espace
  administrateur.
- **`PRIVACY_STUDENT_DATA_RETENTION`** — la durée de vie des classes et des
  comptes élèves, généralement l’année scolaire.
- **`PRIVACY_SECURITY_LOG_RETENTION`** — la durée de vos journaux, fixée par la
  rotation Docker et par votre collecte.

> [!WARNING]
> Une durée annoncée en texte libre qui contredit une durée appliquée rend
> l’information inexacte. Relisez les deux ensemble après chaque changement, et
> alignez la rétention de vos sauvegardes : une sauvegarde conservée au-delà
> contient toujours les données que la purge a effacées.

### Hébergeur et accessibilité

`LEGAL_HOST_*` remplit les mentions légales imposées par la loi pour la
confiance dans l’économie numérique. L’éditeur d’une instance non
professionnelle peut rester anonyme, mais l’hébergeur doit être identifiable.

| Variable                        | Ce qu’elle affiche                                   |
| ------------------------------- | ---------------------------------------------------- |
| `LEGAL_HOST_NAME`               | la raison sociale de l’hébergeur                     |
| `LEGAL_HOST_ADDRESS`            | son adresse postale                                  |
| `LEGAL_HOST_PHONE`              | son numéro de téléphone                              |
| `ACCESSIBILITY_CONTACT`         | le contact pour signaler un défaut d’accessibilité   |
| `ACCESSIBILITY_SCHEME_URL`      | l’URL du schéma pluriannuel de mise en accessibilité |
| `ACCESSIBILITY_ACTION_PLAN_URL` | l’URL du plan d’action annuel                        |

Les deux URL sont validées au démarrage : absolues, sans identifiants, et en
HTTPS lorsque `APP_ENV=production`. Une valeur invalide empêche le démarrage,
et une URL non HTTP(S) s’affiche en texte simple plutôt qu’en lien.

Utilisez des contacts institutionnels ou fonctionnels, jamais l’adresse
personnelle d’un enseignant. Faites valider l’ensemble par l’établissement ou
son DPO : renseigner ces variables ne remplace ni l’inscription au registre des
traitements, ni l’analyse d’impact lorsqu’elle est requise, ni l’information des
élèves et de leurs représentants légaux. L’auto-hébergement ne vaut pas
homologation et les tests automatisés ne remplacent pas un audit RGAA.

## 🧹 Répondre à une demande d’effacement

Les trois niveaux de suppression se font depuis l’interface, sans intervention
en base.

**Un compte élève** — espace enseignant, onglet des élèves. Efface le compte,
son rattachement à la classe et les tentatives encore en cours. Les examens déjà
terminés sont conservés jusqu’à leur échéance, sous le nom enregistré le jour de
l’épreuve, pour qu’une note reste attribuable.

**Une classe entière** — espace enseignant, onglet des classes. Efface la classe
et les élèves qui s’y rattachent.

**Un compte enseignant** — espace administrateur, bouton « Supprimer ». Efface
le compte et tout ce qu’il détient : classes, comptes élèves, banques,
questions, quiz, sessions et copies. L’opération est refusée tant qu’une session
d’examen est en cours ; attendez sa clôture ou terminez-la.

Chaque suppression est tracée dans les journaux de sécurité, sans donnée
personnelle.

> [!WARNING]
> Une sauvegarde prise avant l’effacement contient toujours les données
> supprimées. Alignez la durée de rétention de vos sauvegardes sur celle que
> vous annoncez aux personnes concernées.

## 🔧 Dépannage

Chaque service écrit sur sa sortie standard ; lisez-les séparément :

```shell
docker compose logs --tail 200 open-quiz-backend
docker compose logs --tail 200 open-quiz-database
docker compose logs --tail 200 open-quiz-frontend
```

Le backend y écrit le journal des requêtes, ses erreurs, et les événements
d’audit et de sécurité (`auth.*`, `security.*`), une ligne JSON chacun :
filtrez-les avec `docker compose logs open-quiz-backend | grep '"event"'`.

Les contrôles de santé de `docker compose ps` vérifient :

- `open-quiz-database` : PostgreSQL accepte les connexions (`pg_isready`) ;
- `open-quiz-backend` : `/api/health` répond, ce qui exige une requête réussie
  vers la base ;
- `open-quiz-frontend` : Caddy répond sur `/healthz`, sans interroger l’API.

Pannes fréquentes :

- **Erreurs 503 sous forte charge** : chaque worker de l’API dispose
  d’un nombre limité de connexions à la base ; une requête qui en attend une
  plus de `DATABASE_POOL_TIMEOUT_SECONDS` (10 secondes par défaut) répond 503
  avec le code `SERVER_BUSY` (`Database pool exhausted` dans les journaux),
  comme une image qui attend plus de 30 secondes son tour d’être décodée.
  `/api/health` répond 503 tant que la base est injoignable. Vérifiez les
  requêtes lentes côté PostgreSQL et la mémoire allouée avant d’augmenter
  `OPEN_QUIZ_API_WORKERS` (voir [Plusieurs workers](#plusieurs-workers)).
- **`can't start new thread` ou `fork: Resource temporarily unavailable`** :
  l’API a atteint sa limite de processus. Réglez `OPEN_QUIZ_API_PIDS`
  (environ `100 × workers + 64`) dans le fichier `.env` de la racine.
- **Migration en échec** : l’API ne démarre pas et ses journaux montrent
  l’erreur Alembic ; la migration s’exécute en une transaction, la base est
  donc restée dans son état précédent. `sh ./update.sh --rollback` revient à
  la version précédente (voir
  [Revenir à la version précédente](#revenir-à-la-version-précédente)).

| Symptôme                             | Vérifications                                                                                                        |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| L’API refuse de démarrer             | recherchez une valeur `replace-with-`, vérifiez la longueur et l’unicité des secrets, `APP_ENV` et `FRONTEND_ORIGIN` |
| Une migration échoue au démarrage    | lisez l’erreur Alembic dans les journaux du backend : la base est restée dans son état précédent                     |
| Boucle de redirection HTTP/HTTPS     | vérifiez `FRONTEND_ORIGIN` et les en-têtes de protocole transmis par les proxies                                     |
| Conflit avec le réseau local         | changez `OPEN_QUIZ_SUBNET_PREFIX`, voir « Changer le sous-réseau interne » plus haut                                 |
| Le navigateur bloque les appels API  | faites correspondre l’origine visible et `FRONTEND_ORIGIN`                                                           |
| Un conteneur reste `unhealthy`       | consultez `docker compose ps` puis les journaux des trois services                                                   |
| Le frontend ne trouve pas le backend | vérifiez le réseau Compose et l’état du conteneur `open-quiz-backend`                                                |
| La traduction est indisponible       | utilisez un navigateur et une paire de langues compatibles avec l’API `Translator`                                   |
| Un compte a perdu son TOTP           | utilisez **Récupérer l’accès** ou la commande de secours documentée plus haut                                        |
| L’espace disque augmente             | contrôlez les journaux Docker, les sauvegardes et les durées de conservation                                         |

Si le problème persiste, rassemblez la version, les étapes de reproduction et
les journaux pertinents sans secret ni donnée d’élève, puis ouvrez une issue.
Pour une vulnérabilité, utilisez exclusivement la procédure privée de
[SECURITY.md](../SECURITY.md).
