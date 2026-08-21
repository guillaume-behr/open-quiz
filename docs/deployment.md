# Déployer et exploiter Open Quiz

Ce guide complète le [README principal](../README.md). Il s’adresse aux
personnes qui administrent une instance Open Quiz avec Docker Compose.

> [!IMPORTANT]
> Open Quiz est encore en préversion. Sauvegardez la base et les secrets avant
> chaque mise à jour, puis consultez le [journal des versions](../CHANGELOG.md).

## Sommaire

- [Préparer l’instance](#préparer-linstance)
- [Démarrer les services](#démarrer-les-services)
- [Publier l’application en HTTPS](#publier-lapplication-en-https)
- [Vérifier et surveiller l’instance](#vérifier-et-surveiller-linstance)
- [Sauvegarder les données](#sauvegarder-les-données)
- [Mettre à jour Open Quiz](#mettre-à-jour-open-quiz)
- [Gérer les secrets et les accès](#gérer-les-secrets-et-les-accès)
- [Configurer la conservation et les limites](#configurer-la-conservation-et-les-limites)
- [Renseigner les informations publiques](#renseigner-les-informations-publiques)
- [Dépannage](#dépannage)

## Préparer l’instance

### Prérequis

- Docker Engine avec un plugin Compose prenant en charge `docker compose up --wait` ;
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

1. il génère localement des valeurs aléatoires distinctes pour PostgreSQL, JWT,
   TOTP et le chiffrement des identifiants élèves ;
2. il génère le mot de passe du compte administrateur ;
3. il définit l’origine du frontend en HTTPS et reprend tous les autres réglages
   de production depuis le fichier d’exemple ;
4. il crée `open-quiz-backend/.env` avec des permissions réservées au
   propriétaire ;
5. il lance `update.sh`, qui récupère la dernière version, construit les images,
   démarre les services et attend leur état sain.

Enregistrez immédiatement le mot de passe administrateur affiché par le script :
il ne sera pas réaffiché. L’installation refuse d’écraser un fichier `.env`
existant afin de ne pas remplacer des secrets ou rendre des données chiffrées
illisibles.

Le script ne modifie ni le DNS, ni le pare-feu, ni la configuration TLS ou le
reverse proxy de l’hôte. Configurez ces éléments séparément dans la section
[Publier l’application en HTTPS](#publier-lapplication-en-https).

### Secrets obligatoires

`install.sh` renseigne automatiquement toutes les valeurs obligatoires dans
`open-quiz-backend/.env`.

| Variable                            | Exigence                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------- |
| `JWT_SECRET`                        | valeur aléatoire d’au moins 32 caractères                                 |
| `TOTP_ENCRYPTION_KEY`               | valeur aléatoire distincte d’au moins 32 caractères                       |
| `STUDENT_CREDENTIAL_ENCRYPTION_KEY` | troisième valeur aléatoire distincte d’au moins 32 caractères             |
| `ADMIN_PASSWORD`                    | mot de passe robuste de 16 à 256 caractères, différent des autres secrets |
| `POSTGRES_PASSWORD`                 | mot de passe aléatoire robuste du rôle PostgreSQL                         |

Conservez le fichier généré dans une sauvegarde chiffrée. Ne placez ses valeurs
ni dans Git, ni dans une issue, ni dans les journaux d’exploitation.

Après le premier démarrage, vous pouvez adapter :

- `ADMIN_USERNAME`, l’identifiant du compte administrateur géré par
  l’application ;
- `FRONTEND_ORIGIN`, si le nom de domaine change ; sa valeur doit être l’origine
  HTTPS exacte visible dans le navigateur, sans `/` final.

Conservez `APP_ENV=production` pour une instance publique. Après toute
modification, relancez `sh ./update.sh` et mettez également à jour le reverse
proxy lorsque le domaine change.

Le compte administrateur est créé au premier démarrage. Ensuite,
`ADMIN_USERNAME` et `ADMIN_PASSWORD` continuent de piloter ce même compte : une
modification du mot de passe révoque ses sessions actives.

## Démarrer les services

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

## Publier l’application en HTTPS

Placez un reverse proxy HTTPS devant `127.0.0.1:7800`. Exemple Caddy :

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Pour Nginx, adaptez puis installez
l'[exemple de serveur virtuel](../deployment/nginx.conf). Il inclut la
redirection HTTPS, les en-têtes transmis à l'application et la limite nécessaire
aux imports de questions. Il transmet également la négociation de protocole
nécessaire aux connexions WebSocket. Conservez `proxy_http_version 1.1`, les
en-têtes `Upgrade` et `Connection`, ainsi que le bloc `map` associé : les
requêtes HTTP ordinaires utilisent alors `Connection: close`, tandis qu’une
demande WebSocket utilise `Connection: upgrade`. L’en-tête `Origin`, validé par
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

Le nom de domaine doit correspondre exactement à `FRONTEND_ORIGIN`. En
production, l’API redirige les requêtes qu’elle considère comme HTTP ; conservez
donc les en-têtes de protocole transmis par les reverse proxies.

Par défaut, le frontend et l’API partagent la même origine. Si l’API est servie
sur une autre origine, définissez `VITE_API_URL` lors de la construction :

```shell
VITE_API_URL=https://api.example.com docker compose up --detach --build
```

Conservez `FRONTEND_ORIGIN` égal à l’origine du frontend visible dans le
navigateur, par exemple `https://quiz.example.com`. Le conteneur frontend ajoute
`VITE_API_URL` à sa politique CSP et le backend autorise l’origine frontend par
CORS.

Si le reverse proxy externe limite la taille des requêtes, prévoyez jusqu’à
96 Mio pour les routes authentifiées de création, modification et import de
questions. Les requêtes ordinaires restent limitées par
`MAX_REQUEST_BODY_BYTES`.

## Vérifier et surveiller l’instance

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
  `auth.refresh_reuse_detected`.

Les journaux peuvent contenir des informations d’audit. Centralisez-les dans un
espace à accès restreint et appliquez la durée de conservation validée pour
votre instance.

## Sauvegarder les données

Une sauvegarde exploitable comprend :

1. une sauvegarde logique cohérente de la base PostgreSQL ;
2. une copie protégée de `open-quiz-backend/.env` ;
3. la version ou le commit Open Quiz correspondant.

`TOTP_ENCRYPTION_KEY` et `STUDENT_CREDENTIAL_ENCRYPTION_KEY` ne sont pas
stockées dans la base. Sans le fichier `.env` correspondant, une restauration
de la base reste incomplète.

### Sauvegarde PostgreSQL en fonctionnement

`pg_dump` produit une sauvegarde cohérente sans arrêter l’application. Créez
directement une archive au format personnalisé hors du conteneur :

```shell
mkdir -p backups
docker compose exec -T open-quiz-database \
    pg_dump --username=open_quiz --dbname=open_quiz --format=custom \
    > backups/open-quiz.dump
```

Déplacez ensuite la sauvegarde vers un stockage distinct, chiffré et protégé.
Vérifiez-la avec `pg_restore --list backups/open-quiz.dump` et testez
régulièrement une restauration dans une instance isolée.

### Tester une restauration

Sur une instance de test arrêtée et après avoir conservé sa base actuelle :

> [!WARNING]
> N’ajoutez jamais `--volumes` à `docker compose down` pendant une
> restauration : cette option supprime le volume de données.

```shell
docker compose down
docker compose up --detach --wait open-quiz-database
docker compose exec -T open-quiz-database \
    pg_restore --username=open_quiz --dbname=open_quiz \
    --clean --if-exists --no-owner < backups/open-quiz.dump
docker compose up --detach --wait
docker compose ps
```

Utilisez le fichier `.env` correspondant à la sauvegarde, puis vérifiez
`/api/health`, les connexions et un échantillon de résultats. Une restauration
en production suit le même principe uniquement après validation complète sur
l’instance isolée.

> [!CAUTION]
> Une restauration remplace les données actuelles. Arrêtez les écritures,
> conservez une copie supplémentaire de l’état présent et validez la procédure
> sur une instance de test avant toute restauration en production.

## Mettre à jour Open Quiz

Avant une mise à jour :

1. lisez le [journal des versions](../CHANGELOG.md) ;
2. sauvegardez la base et le fichier `.env` ;
3. vérifiez que le dépôt ne contient aucune modification locale à préserver.

Sous Unix :

```shell
sh ./update.sh
```

Sous PowerShell :

```powershell
./update.ps1
```

Les scripts effectuent un `git pull --ff-only`, valident la configuration
Compose, reconstruisent les conteneurs, attendent leur état sain puis affichent
leur statut. Cette version ne migre pas les anciennes bases : utilisez un volume
PostgreSQL neuf pour la transition.

Après la mise à jour, vérifiez `docker compose ps`, `/api/health`, la connexion
des trois rôles et les journaux du backend.

## Gérer les secrets et les accès

### Effet d’une rotation

| Élément                             | Effet d’un changement                                                             |
| ----------------------------------- | --------------------------------------------------------------------------------- |
| `JWT_SECRET`                        | invalide les jetons d’accès et révoque les sessions longues au prochain démarrage |
| `ADMIN_PASSWORD`                    | remplace le mot de passe administrateur et révoque ses sessions                   |
| `TOTP_ENCRYPTION_KEY`               | impose une nouvelle inscription TOTP à tous les comptes privilégiés               |
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

## Configurer la conservation et les limites

Les valeurs ci-dessous sont fournies dans les fichiers `.env` d’exemple.

| Variable                        | Rôle                                                    | Défaut                                          |
| ------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| `ACCESS_TOKEN_MINUTES`          | durée des jetons d’accès privilégiés                    | `15`                                            |
| `REFRESH_TOKEN_DAYS`            | durée maximale d’une session longue                     | `7`                                             |
| `LOGIN_ATTEMPTS`                | tentatives par compte et par fenêtre                    | `5`                                             |
| `LOGIN_WINDOW_SECONDS`          | fenêtre des tentatives par compte                       | `900`                                           |
| `GLOBAL_LOGIN_ATTEMPTS`         | tentatives de connexion pour toute l’instance           | `500`                                           |
| `GLOBAL_LOGIN_WINDOW_SECONDS`   | fenêtre du quota global                                 | `60`                                            |
| `QUIZ_JOIN_ATTEMPTS`            | tentatives pour rejoindre une session                   | `20`                                            |
| `QUIZ_PARTICIPANT_ATTEMPTS`     | requêtes d’un participant par fenêtre                   | `240`                                           |
| `QUIZ_VIOLATION_ATTEMPTS`       | alertes de surveillance par fenêtre                     | `20`                                            |
| `QUIZ_RATE_WINDOW_SECONDS`      | fenêtre des limites liées aux quiz                      | `60`                                            |
| `QUIZ_RESULT_RETENTION_DAYS`    | conservation des résultats terminés                     | `365`                                           |
| `PROBLEM_REPORT_ATTEMPTS`       | signalements anonymes par fenêtre pour toute l’instance | `30` en local, `5` dans l’exemple de production |
| `PROBLEM_REPORT_WINDOW_SECONDS` | fenêtre du quota de signalements                        | `900`                                           |
| `PROBLEM_REPORT_RETENTION_DAYS` | conservation des signalements                           | `90`                                            |
| `MAX_REQUEST_BODY_BYTES`        | taille des requêtes applicatives ordinaires             | `65536`                                         |

La suppression des données expirées est appliquée au démarrage, puis toutes les
heures. Adaptez ces valeurs à la politique validée pour votre instance avant de
collecter des données réelles.

`MAX_REQUEST_BODY_BYTES` ne couvre pas les routes authentifiées de création,
modification et import de questions : elles disposent d’une limite de 96 Mio
pour transporter les images encodées.

## Renseigner les informations publiques

Les pages `/legal-notice`, `/privacy`, `/accessibility` et `/cookie-settings`
chargent les informations publiques depuis l’API. Une valeur absente ne bloque
pas le démarrage, mais laisse apparaître un avertissement dans l’interface.

| Groupe          | Variables                                                                                                                   |
| --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Hébergeur       | `LEGAL_HOST_NAME`, `LEGAL_HOST_ADDRESS`, `LEGAL_HOST_PHONE`                                                                 |
| Confidentialité | `PRIVACY_CONTROLLER_NAME`, `PRIVACY_CONTROLLER_CONTACT`, `PRIVACY_DPO_CONTACT`, `PRIVACY_LEGAL_BASIS`, `PRIVACY_RECIPIENTS` |
| Conservation    | `PRIVACY_TEACHER_DATA_RETENTION`, `PRIVACY_STUDENT_DATA_RETENTION`, `PRIVACY_SECURITY_LOG_RETENTION`                        |
| Accessibilité   | `ACCESSIBILITY_CONTACT`, `ACCESSIBILITY_SCHEME_URL`, `ACCESSIBILITY_ACTION_PLAN_URL`                                        |

Utilisez des contacts institutionnels ou fonctionnels, jamais l’adresse
personnelle d’un enseignant. Faites valider le contenu par l’établissement ou
son DPO. L’auto-hébergement ne vaut pas homologation et les tests automatisés ne
remplacent pas un audit RGAA.

## Dépannage

| Symptôme                             | Vérifications                                                                                                        |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| L’API refuse de démarrer             | recherchez une valeur `replace-with-`, vérifiez la longueur et l’unicité des secrets, `APP_ENV` et `FRONTEND_ORIGIN` |
| Boucle de redirection HTTP/HTTPS     | vérifiez `FRONTEND_ORIGIN` et les en-têtes de protocole transmis par les proxies                                     |
| Le navigateur bloque les appels API  | faites correspondre l’origine visible, `FRONTEND_ORIGIN`, `VITE_API_URL`, CORS et CSP                                |
| Un conteneur reste `unhealthy`       | consultez `docker compose ps` puis les journaux des trois services                                                   |
| Le frontend ne trouve pas le backend | vérifiez le réseau Compose et laissez `VITE_API_URL` vide pour le déploiement fourni                                 |
| La traduction est indisponible       | utilisez un navigateur et une paire de langues compatibles avec l’API `Translator`                                   |
| Un compte a perdu son TOTP           | utilisez **Récupérer l’accès** ou la commande de secours documentée plus haut                                        |
| L’espace disque augmente             | contrôlez les journaux Docker, les sauvegardes et les durées de conservation                                         |

Si le problème persiste, rassemblez la version, les étapes de reproduction et
les journaux pertinents sans secret ni donnée d’élève, puis ouvrez une issue.
Pour une vulnérabilité, utilisez exclusivement la procédure privée de
[SECURITY.md](../SECURITY.md).
