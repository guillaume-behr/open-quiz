# Interface Open Quiz

Application React et TypeScript d’Open Quiz. Elle fournit les espaces élève,
enseignant et administrateur, puis communique avec l’API FastAPI par HTTP et
WebSocket.

Consultez aussi le [README principal](../README.md), le
[guide de contribution](../CONTRIBUTING.md) et le
[guide de déploiement](../docs/deployment.md).

## 🧰 Technologies

- React 19 et React Router ;
- TypeScript, Vite et Tailwind CSS ;
- i18next pour les huit langues de l’interface ;
- Playwright pour les parcours navigateur ;
- Pyodide pour l’exécution locale de Python.

## 💻 Développement local

Cette procédure lance le serveur Vite pour modifier et tester l’interface. Elle
ne remplace pas l’installation Docker Compose recommandée pour utiliser une
instance.

### Prérequis

- Node.js 24 ;
- Corepack ;
- pnpm 11.15.1 ;
- le backend lancé sur `http://localhost:8000` pour utiliser l’application
  manuellement.

Depuis le dossier `open-quiz-frontend` :

```shell
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrez `http://localhost:5173`. Vite transmet les requêtes HTTP et WebSocket
commençant par `/api` au backend local.

## ⚙️ Configuration

| Variable                | Portée                        | Défaut                  | Usage                                       |
| ----------------------- | ----------------------------- | ----------------------- | ------------------------------------------- |
| `VITE_API_URL`          | navigateur, à la compilation  | vide                    | origine absolue d’une API servie séparément |
| `VITE_API_PROXY_TARGET` | serveur Vite de développement | `http://localhost:8000` | cible du proxy HTTP et WebSocket            |

Laissez `VITE_API_URL` vide avec le proxy Vite ou le déploiement Caddy fourni.
Pour utiliser un autre backend pendant le développement :

```shell
VITE_API_PROXY_TARGET=http://localhost:9000 pnpm dev
```

`VITE_API_PROXY_TARGET` est lu depuis l’environnement du processus qui démarre
Vite. `VITE_API_URL` est intégré au bundle client : comme toute variable
`VITE_*`, elle est publique et ne doit jamais contenir de secret.

## ⌨️ Commandes disponibles

| Commande            | Rôle                                                     |
| ------------------- | -------------------------------------------------------- |
| `pnpm dev`          | démarre Vite avec le proxy de développement              |
| `pnpm build`        | vérifie les types puis produit `dist/`                   |
| `pnpm preview`      | sert le build localement, sans le proxy de développement |
| `pnpm lint`         | exécute ESLint                                           |
| `pnpm format`       | applique Prettier aux sources et catalogues              |
| `pnpm format:check` | vérifie le formatage                                     |
| `pnpm test`         | valide les huit catalogues et les étiquettes de classe   |
| `pnpm typecheck`    | vérifie `src/` et la configuration Vite                  |
| `pnpm test:e2e`     | lance les parcours Playwright dans Chromium              |
| `pnpm test:e2e:ui`  | ouvre l’interface Playwright                             |

`pnpm preview` ne transmet pas `/api`. Pour tester un build complet, fournissez
une valeur `VITE_API_URL` au moment de la compilation ou utilisez les
conteneurs du projet.

## 🗺️ Routes

### Espaces applicatifs

| Route                | Usage                                             |
| -------------------- | ------------------------------------------------- |
| `/student/login`     | connexion d’un élève                              |
| `/student/dashboard` | examens, entraînements et rattrapages disponibles |
| `/student/results`   | historique des résultats de l’élève               |
| `/student/exam`      | exécution ou reprise d’un examen déjà rejoint     |
| `/student/training`  | exécution ou reprise d’un entraînement            |
| `/teacher/login`     | connexion et validation TOTP d’un enseignant      |
| `/teacher/dashboard` | élèves, classes, contenus, sessions et résultats  |
| `/admin/dashboard`   | comptes enseignants et signalements               |

| Route                                  | Usage                     |
| -------------------------------------- | ------------------------- |
| `/teacher/session-display/:sessionKey` | code et minuteur agrandis |

La vue agrandie est ouverte par le bouton « Agrandir » d’une session en cours.
Elle ne s’authentifie pas : elle reçoit ses mises à jour de l’onglet du tableau
de bord, qui doit rester ouvert.

La saisie d’un code d’examen se fait depuis le tableau de bord élève.
`/student/exam` redirige l’utilisateur lorsqu’aucune session valide n’est
enregistrée. La route `/` redirige vers `/student/login`.

### Pages publiques

- `/legal-notice` ;
- `/privacy` ;
- `/accessibility` ;
- `/cookie-settings` ;
- `/report-a-problem`.

Toute route inconnue affiche la page 404.

## 🗂️ Organisation du code

```text
src/
├── api/          client HTTP, types et rotation des sessions
├── components/   composants d’interface et fonctionnalités métier
├── layouts/      structure commune des pages
├── lib/          traduction, mises à jour temps réel et utilitaires
└── pages/        points d’entrée chargés à la demande

public/
├── locales/      catalogues i18next
└── pyodide/      runtime Python servi localement

tests/e2e/        parcours Playwright
```

Les règles métier, les autorisations, les tirages et la notation restent côté
backend. Le frontend conserve les jetons d’accès privilégiés en mémoire et les
sessions élève dans `sessionStorage`. Les sessions longues des enseignants et
administrateurs utilisent un cookie HttpOnly géré par l’API.

## 🧪 Tests navigateur

Installez Chromium une première fois, puis lancez les tests :

```shell
pnpm exec playwright install chromium
pnpm test:e2e
```

Playwright démarre automatiquement :

- un serveur réseau de test sur `127.0.0.1:4180` ;
- Vite sur `127.0.0.1:4173` ;
- Chromium avec les API majoritairement simulées.

Le backend FastAPI n’est donc pas nécessaire pour cette suite. Les ports 4173
et 4180 doivent être disponibles. Les tests couvrent aussi le proxy HTTP et
WebSocket local.

La CI principale exécute ESLint, Prettier, la validation des catalogues, le
typecheck, le build et l’audit des dépendances. Les tests E2E restent une
vérification locale distincte.

## 🌍 Internationalisation

Les catalogues se trouvent dans `public/locales/<langue>/translation.json`.
L’anglais sert de référence structurelle et l’interface prend actuellement en
charge le français, l’anglais, l’allemand, l’espagnol, le portugais,
l’ukrainien, l’arabe et le chinois simplifié.

Pour ajouter une langue :

1. créez son catalogue à partir de `public/locales/en/translation.json` ;
2. ajoutez son code et son libellé à `availableLanguages` dans
   `src/lib/i18n.ts` ;
3. traduisez toutes les valeurs sans modifier les variables `{{...}}` ni les
   suffixes de pluriel ;
4. exécutez `pnpm test` puis `pnpm format:check`.

`pnpm test` détecte les clés manquantes ou inattendues, les valeurs non
textuelles, les variables d’interpolation différentes et les traductions
restées identiques à l’anglais hors liste autorisée.

## 🔠 Traduction des quiz

Lorsque la langue d’origine du quiz diffère de celle de l’interface, l’élève
peut demander une traduction du titre, des questions et des réponses. Le code
n’est jamais traduit et le contenu original reste accessible.

La traduction utilise l’API `Translator` du navigateur. Elle ne démarre qu’à la
demande de l’élève et peut provoquer le téléchargement d’un modèle par le
navigateur. Aucun fournisseur distant ni aucune clé d’API ne sont configurés
par Open Quiz. Si le navigateur ou la paire de langues n’est pas compatible,
le contenu original reste affiché.

## 🐍 Exécution Python

Les courts extraits Python s’exécutent avec les ressources Pyodide fournies
dans `public/pyodide`. Le runtime est chargé dans un Web Worker, puis les API
réseau et la création de Workers supplémentaires sont désactivées.

Les limites actuelles sont :

- 20 000 caractères de code source ;
- 60 secondes pour initialiser Pyodide ;
- 10 secondes d’exécution ;
- 1 000 000 de caractères en sortie.

Une expiration ou un dépassement de sortie termine le Worker afin de ne pas
bloquer l’interface.

## 🚀 Production

Le `Dockerfile` compile l’application avec Node.js puis sert `dist/` avec Caddy
sur le port 8080. Le conteneur :

- expose `/healthz` pour son contrôle de disponibilité ;
- transmet `/api/*` au service `open-quiz-backend` ;
- applique la politique CSP et les principaux en-têtes de sécurité ;
- renvoie les routes inconnues vers `index.html` pour React Router.

Un hébergement alternatif doit reproduire le fallback SPA et transmettre les
connexions WebSocket. Le déploiement de référence est décrit dans
[`docs/deployment.md`](../docs/deployment.md).

## 🤝 Contribution

Avant un changement, consultez [CONTRIBUTING.md](../CONTRIBUTING.md). Signalez
les vulnérabilités selon [SECURITY.md](../SECURITY.md), jamais dans une issue
publique. Le projet est distribué sous [licence MIT](../LICENSE).
