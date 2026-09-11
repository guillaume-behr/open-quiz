<h1><img src=".github/assets/open-quiz-wordmark.svg" alt="Open Quiz" width="230"></h1>

[![CI](https://github.com/guillaume-behr/open-quiz/actions/workflows/security.yml/badge.svg)](https://github.com/guillaume-behr/open-quiz/actions/workflows/security.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Plateforme libre et auto-hébergeable permettant de créer des quiz,
d’organiser des examens en classe et de proposer des entraînements aux
élèves.

Open Quiz réunit trois espaces dans une même application : l’administrateur
gère les enseignants, les enseignants préparent les contenus et les sessions,
et les élèves passent leurs examens ou s’entraînent depuis leur tableau de bord.

## 📖 Sommaire

- [Fonctionnalités](#-fonctionnalités)
- [Installation](#-installation)
- [Premiers pas](#-premiers-pas)
- [Développement](#-développement)
- [Documentation](#-documentation)

## ✨ Fonctionnalités

Open Quiz ne présuppose aucune discipline. Quelle que soit la matière, une
session suit toujours le même déroulement :

1. l’administrateur crée les comptes enseignants ;
2. l’enseignant crée ses élèves, ses classes et ses banques de questions ;
3. il prépare un examen, ou ouvre des banques à l’entraînement ;
4. les élèves se connectent et rejoignent leur activité ;
5. l’enseignant corrige les réponses rédactionnelles, puis publie les notes ou
   les exporte.

### Banques de questions

- choix unique, choix multiple et réponse rédactionnelle ;
- énoncés illustrés d’images, extraits de code mis en forme, et réponse
  attendue dans un langage donné ;
- questions réparties en trois niveaux de difficulté, dans lesquels chaque quiz
  pioche selon le barème que vous lui fixez ;
- points définis proposition par proposition, avec points négatifs facultatifs ;
- import et export JSON d’une banque complète, images comprises, en une seule
  transaction : rien n’est créé si une ligne est invalide.

### Examens

- salle d’attente, minuteur, pause et reprise pour toute la classe ;
- même tirage pour tout le monde, ou sujet individuel tiré par élève ;
- relecture facultative de la copie avant la remise définitive ;
- l’enseignant est prévenu si un élève quitte le plein écran, change d’onglet,
  copie, colle ou lance une impression : ces alertes sont informatives et ne
  déclenchent jamais de sanction automatique ;
- rattrapage : faire repasser à des élèves choisis une sélection d’examens
  déjà passés ;
- sujets papier nominatifs en A4, au tirage déterministe : un même élève
  retrouve le même sujet ;
- affichage agrandi du code de session et du minuteur, à projeter à la classe.

### Correction et notes

- correction automatique des questions à choix, manuelle pour les réponses
  rédactionnelles ;
- l’élève voit sa correction à titre provisoire, et la publication fige la
  note ;
- export CSV des résultats, et suppression immédiate d’un résultat par
  l’enseignant.

### Entraînement et expérience élève

- banques ouvertes à l’entraînement classe par classe, avec le nombre de
  questions de votre choix, relançables librement ;
- correction immédiate et historique de progression ;
- compte personnel et tableau de bord dédié ;
- interface claire ou sombre, disponible en huit langues ;
- traduction du quiz sur l’appareil de l’élève, lorsque son navigateur la prend
  en charge ;
- exécution de courts extraits Python dans le navigateur, avec Pyodide.

### Hébergement et données personnelles

- déploiement autonome avec Docker Compose, Caddy et PostgreSQL ;
- mots de passe Argon2, TOTP pour les comptes privilégiés, cookies HttpOnly et
  limites de débit ;
- aucune adresse IP traitée, aucun service tiers appelé, aucune mesure
  d’audience ni publicité ;
- durées de conservation appliquées automatiquement, et pages légales à
  renseigner instance par instance.

## 📦 Installation

Docker Compose est la méthode recommandée pour installer et utiliser Open Quiz.
Cette section couvre le premier démarrage. Le
[guide de déploiement et d’exploitation](docs/deployment.md) détaille la mise en
production, les sauvegardes, la rotation des secrets et le dépannage.

### Prérequis

- Docker avec le plugin Compose ;
- Git et un shell compatible POSIX (Linux, macOS ou WSL sous Windows) ;
- un nom de domaine valide, ainsi qu’un reverse proxy HTTPS pour rendre
  l’instance publique.

### 1. Récupérer le projet

```shell
git clone https://github.com/guillaume-behr/open-quiz.git
cd open-quiz
```

### 2. Lancer l’installation guidée

```shell
sh ./install.sh
```

Le script demande le nom de domaine, sans `https://` ni `/` final. Il génère
les secrets et le mot de passe administrateur, écrit
`open-quiz-backend/.env`, puis construit et démarre les conteneurs. Passez
`--domain quiz.example.com` pour une installation non interactive, et
`--help` pour les autres options.

> [!IMPORTANT]
> Le mot de passe administrateur n’est affiché qu’une seule fois. Enregistrez-le
> avant de fermer le terminal.

Sur un déploiement déjà installé, l’installation refuse d’écraser la
configuration existante : utilisez `sh ./update.sh`. Le guide de déploiement
[détaille chaque étape du script](docs/deployment.md#-préparer-linstance).

### 3. Publier l’instance en HTTPS

L’installation configure Open Quiz, mais ni le DNS, ni le certificat TLS, ni le
reverse proxy de la machine. Le frontend écoute uniquement sur
`127.0.0.1:7800` : placez un reverse proxy HTTPS devant ce port, par exemple
avec Caddy.

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Un [exemple de configuration Nginx](docs/nginx.conf) est également fourni ;
remplacez son domaine et ses chemins de certificats avant de l’activer. Le
[guide de déploiement](docs/deployment.md#-publier-lapplication-en-https) décrit
les en-têtes à transmettre, notamment pour les connexions WebSocket.

### 4. Vérifier l’instance

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est `{"status":"ok"}`.

L’instance est installée. La suite — première connexion, mentions RGPD et
premier examen — se trouve dans [Premiers pas](#-premiers-pas).

### Mises à jour

```shell
sh ./update.sh
```

Le [guide de déploiement](docs/deployment.md#-mettre-à-jour-open-quiz) décrit le
déroulement complet de la mise à jour, ainsi que l’option `--no-pull` pour
reconstruire sans récupérer de nouvelle révision.

> [!CAUTION]
> Sauvegardez PostgreSQL et `open-quiz-backend/.env` avant chaque mise à jour.
> Les procédures de sauvegarde, de restauration et de rotation des secrets sont
> décrites dans le
> [guide de déploiement](docs/deployment.md#-sauvegarder-les-données).

## 🚀 Premiers pas

L’instance démarre vide : un seul compte administrateur existe, et rien d’autre.
Les quatre étapes ci-dessous mènent de là au premier examen.

Les chemins s’ajoutent au domaine configuré pendant l’installation. En
développement local, utilisez `http://localhost:5173`.

| Espace         | Chemin             | Qui s’y connecte                       |
| -------------- | ------------------ | -------------------------------------- |
| Administration | `/admin/dashboard` | le compte créé par l’installation      |
| Enseignant     | `/teacher/login`   | les comptes créés par l’administrateur |
| Élève          | `/student/login`   | les comptes créés par un enseignant    |

### 1. Se connecter comme administrateur

Rendez-vous sur `/admin/dashboard` avec les identifiants affichés pendant
l’installation, puis configurez immédiatement la double authentification : elle
est obligatoire pour les comptes privilégiés.

L’administrateur ne crée ni contenu ni élève. Il gère les comptes enseignants
et les signalements de problèmes.

### 2. Renseigner les mentions RGPD

Les pages `/privacy`, `/legal-notice` et `/accessibility` n’embarquent aucun
texte propre à votre établissement : elles affichent ce que vous déclarez ici.
Tant qu’une valeur reste vide, la page affiche « Non renseigné » en rouge, et
l’instance publie une politique de confidentialité sans responsable
identifiable.

Ces variables ne sont pas des secrets, mais elles se placent dans le même
fichier que le reste de la configuration :

```shell
$EDITOR open-quiz-backend/.env
sh ./update.sh
```

Identité de l’hébergeur, exigée pour les mentions légales :

| Variable             | Ce qu’elle publie                |
| -------------------- | -------------------------------- |
| `LEGAL_HOST_NAME`    | la raison sociale de l’hébergeur |
| `LEGAL_HOST_ADDRESS` | son adresse postale              |
| `LEGAL_HOST_PHONE`   | son numéro de téléphone          |

Responsable du traitement et exercice des droits, exigés par les articles 13
et 14 du RGPD :

| Variable                     | Ce qu’elle publie                         |
| ---------------------------- | ----------------------------------------- |
| `PRIVACY_CONTROLLER_NAME`    | l’établissement responsable du traitement |
| `PRIVACY_CONTROLLER_CONTACT` | l’adresse où exercer ses droits           |
| `PRIVACY_LEGAL_BASIS`        | la base légale retenue, en toutes lettres |
| `PRIVACY_RECIPIENTS`         | qui accède aux données, hébergeur compris |

Ce sont les sept valeurs sans lesquelles les pages publiques restent
incomplètes. Les durées appliquées par la purge — résultats d’examens,
entraînements, signalements — ont déjà une valeur par défaut et s’affichent
toutes seules : vous n’avez rien à recopier.

Restent facultatives pour le logiciel : le contact du DPO, les deux URL
d’accessibilité, et les trois durées que vous annoncez en toutes lettres pour
ce que la purge ne couvre pas, comme la durée de vie d’un compte élève. Le
guide de déploiement
[décrit chacune](docs/deployment.md#-configurer-les-mentions-rgpd-et-légales),
et l’API énumère au démarrage celles qu’elle juge obligatoires, sous
l’événement `security.public_information_incomplete`.

### 3. Créer un compte enseignant

Depuis le tableau de bord d’administration, créez le compte et transmettez ses
identifiants à l’enseignant. À sa première connexion sur `/teacher/login`, il
configure à son tour sa double authentification.

### 4. Préparer et lancer une activité

L’enseignant travaille ensuite depuis son propre espace : il crée ses classes
et ses comptes élèves, remplit ses banques de questions, puis lance un examen
ou ouvre des banques à l’entraînement. Les élèves se connectent sur
`/student/login` avec les identifiants qu’il leur remet.

> [!CAUTION]
> L’auto-hébergement ne vaut ni homologation, ni conformité automatique. Avant
> d’ouvrir l’instance à des élèves, faites valider la base légale, les durées de
> conservation, les sous-traitants et l’information des utilisateurs par
> l’établissement ou son DPO. Conservez la mention « Accessibilité : non
> conforme » tant qu’aucun audit RGAA complet n’a été réalisé.

## 🛠️ Développement

Pour installer une instance à utiliser, suivez la procédure
[Installation](#-installation). Pour travailler sur le code, un script prépare
les secrets de développement et démarre PostgreSQL :

```shell
sh ./install-dev.sh
```

L’API se lance ensuite avec `uv run fastapi dev main.py` depuis
`open-quiz-backend`, et l’interface avec `pnpm dev` depuis
`open-quiz-frontend`.

Le [guide de contribution](CONTRIBUTING.md#-préparer-lenvironnement-de-développement)
détaille les prérequis, le rôle de chaque script et les vérifications à
exécuter avant une pull request.

## 📚 Documentation

| Ressource                                              | Contenu                                            |
| ------------------------------------------------------ | -------------------------------------------------- |
| [Déploiement et exploitation](docs/deployment.md)      | production, sauvegardes, mises à jour et dépannage |
| [Documentation backend](open-quiz-backend/README.md)   | API, sécurité, stockage et exploitation            |
| [Documentation frontend](open-quiz-frontend/README.md) | interface, routes, traduction et tests navigateur  |
| [Guide de contribution](CONTRIBUTING.md)               | environnement, conventions et vérifications        |
| [Politique de sécurité](SECURITY.md)                   | procédure privée de signalement                    |

## ⚖️ Licence

Open Quiz est distribué sous [licence MIT](LICENSE).
