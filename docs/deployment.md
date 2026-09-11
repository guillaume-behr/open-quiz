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

1. il génère localement des valeurs aléatoires distinctes pour PostgreSQL, JWT,
   TOTP et le chiffrement des identifiants élèves ;
2. il génère le mot de passe du compte administrateur ;
3. il définit l’origine du frontend en HTTPS et reprend tous les autres réglages
   de production depuis le fichier d’exemple ;
4. il crée `open-quiz-backend/.env` avec des permissions réservées au
   propriétaire ;
5. il lance `update.sh --no-pull`, qui construit les images, démarre les
   services et attend leur état sain. Le clone est déjà à jour, donc aucune
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

Tous les secrets vivent dans `open-quiz-backend/.env`, que Git ignore.
`install.sh` les génère au premier démarrage : vous n’avez rien à écrire
vous-même.

| Variable                            | Rôle                                               | Exigence                                   |
| ----------------------------------- | -------------------------------------------------- | ------------------------------------------ |
| `POSTGRES_PASSWORD`                 | mot de passe du rôle PostgreSQL                    | valeur aléatoire robuste                   |
| `DATABASE_URL`                      | accès à la base depuis l’API                       | URL PostgreSQL SQLAlchemy                  |
| `JWT_SECRET`                        | signature des jetons de session                    | 32 caractères aléatoires au moins          |
| `TOTP_ENCRYPTION_KEY`               | chiffrement des secrets de double authentification | 32 caractères, distincts du secret JWT     |
| `STUDENT_CREDENTIAL_ENCRYPTION_KEY` | chiffrement des mots de passe élèves relisibles    | 32 caractères, distincts des deux autres   |
| `ADMIN_PASSWORD`                    | mot de passe du compte administrateur              | 16 à 256 caractères, différent des secrets |

Les trois clés doivent être distinctes les unes des autres : l’API refuse de
démarrer si deux d’entre elles coïncident, ou si l’une a gardé sa valeur
d’exemple.

> [!CAUTION]
> Conservez `.env` dans une sauvegarde chiffrée. Ne placez jamais ses valeurs
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
  `auth.refresh_reuse_detected`.

Les journaux peuvent contenir des informations d’audit. Centralisez-les dans un
espace à accès restreint et appliquez la durée de conservation validée pour
votre instance.

## 💾 Sauvegarder les données

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

## ⬆️ Mettre à jour Open Quiz

Avant une mise à jour :

1. lisez les notes de la release visée ;
2. sauvegardez la base et le fichier `.env` ;
3. vérifiez que le dépôt ne contient aucune modification locale à préserver.

```shell
sh ./update.sh
```

Le script vérifie d’abord que Docker est accessible, que
`open-quiz-backend/.env` existe et que le dépôt ne contient aucune modification
locale, puis effectue un `git pull --ff-only`. Il affiche la révision avant et
après la mise à jour et rappelle de sauvegarder PostgreSQL lorsqu’elle change.
Il valide ensuite la configuration Compose, reconstruit les conteneurs, attend
leur état sain et affiche leur statut ainsi que l’origine publique configurée.

Pour reconstruire et redémarrer sans récupérer de révision, par exemple après
avoir modifié `.env` :

```shell
sh ./update.sh --no-pull
```

Cette version ne migre pas les anciennes bases : utilisez un volume PostgreSQL
neuf pour la transition.

Après la mise à jour, vérifiez `docker compose ps`, `/api/health`, la connexion
des trois rôles et les journaux du backend.

## 🔑 Gérer les secrets et les accès

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

## ⏳ Configurer la conservation et les limites

Les valeurs ci-dessous sont fournies dans les fichiers `.env` d’exemple.

| Variable                           | Rôle                                                    | Défaut                                          |
| ---------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| `ACCESS_TOKEN_MINUTES`             | durée des jetons d’accès privilégiés                    | `15`                                            |
| `REFRESH_TOKEN_DAYS`               | durée maximale d’une session longue                     | `7`                                             |
| `LOGIN_ATTEMPTS`                   | tentatives par compte et par fenêtre                    | `10`                                            |
| `LOGIN_WINDOW_SECONDS`             | fenêtre des tentatives par compte                       | `900`                                           |
| `GLOBAL_LOGIN_ATTEMPTS`            | tentatives de connexion pour toute l’instance           | `2000`                                          |
| `GLOBAL_LOGIN_WINDOW_SECONDS`      | fenêtre du quota global                                 | `60`                                            |
| `QUIZ_JOIN_ATTEMPTS`               | tentatives pour rejoindre une session                   | `60`                                            |
| `QUIZ_PARTICIPANT_ATTEMPTS`        | requêtes d’un participant par fenêtre                   | `900`                                           |
| `QUIZ_VIOLATION_ATTEMPTS`          | alertes de surveillance par fenêtre                     | `60`                                            |
| `QUIZ_RATE_WINDOW_SECONDS`         | fenêtre des limites liées aux quiz                      | `60`                                            |
| `QUIZ_RESULT_RETENTION_DAYS`       | conservation des résultats terminés                     | `365`                                           |
| `TRAINING_RESULT_RETENTION_DAYS`   | conservation des entraînements terminés                 | `365`                                           |
| `ABANDONED_SESSION_RETENTION_DAYS` | délai avant de solder une session jamais clôturée       | `7`                                             |
| `PROBLEM_REPORT_ATTEMPTS`          | signalements anonymes par fenêtre pour toute l’instance | `60` en local, `5` dans l’exemple de production |
| `PROBLEM_REPORT_WINDOW_SECONDS`    | fenêtre du quota de signalements                        | `900`                                           |
| `PROBLEM_REPORT_RETENTION_DAYS`    | conservation des signalements                           | `90`                                            |
| `MAX_REQUEST_BODY_BYTES`           | taille des requêtes applicatives ordinaires             | `65536`                                         |

La suppression des données expirées est appliquée au démarrage, puis toutes les
heures. Adaptez ces valeurs à la politique validée pour votre instance avant de
collecter des données réelles.

Une session n’est clôturée par son enseignant que lorsqu’il ouvre son tableau
de bord. Passé `ABANDONED_SESSION_RETENTION_DAYS`, la maintenance s’en charge à
sa place : un examen qui a recueilli des réponses est noté puis conservé au
titre de `QUIZ_RESULT_RETENTION_DAYS`, tandis qu’une salle d’attente sans
réponse et les entraînements interrompus sont supprimés. Un enseignant
désactivé ou parti ne laisse donc plus de données sans terme.

`MAX_REQUEST_BODY_BYTES` ne couvre pas les routes authentifiées de création,
modification et import de questions : elles disposent d’une limite de 96 Mio
pour transporter les images encodées.

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
`security.public_information_incomplete`. Le contact du DPO et les deux URL
d’accessibilité en sont exclus : ils restent facultatifs pour le logiciel, pas
nécessairement pour vous.

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
