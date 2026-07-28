# Open Quiz

Open Quiz est une application de quiz en classe. Elle permet aux enseignants de
gérer des classes et des banques de questions, de lancer des sessions en direct,
de surveiller leur déroulement et de corriger les réponses rédactionnelles. Les
élèves rejoignent une session avec un code et leur identifiant de classe, sans
créer de compte.

Le dépôt contient :

- `open-quiz-backend` : API FastAPI, authentification 2FA et base SQLite ;
- `open-quiz-frontend` : interface React/Vite, traductions et exécution locale
  de courts extraits Python ;
- `docker-compose.yml` : déploiement autonome derrière Caddy.

## Développement local

Prérequis : Python 3.14, [uv](https://docs.astral.sh/uv/), Node.js 24 et
Corepack/pnpm.

### 1. Backend

Depuis `open-quiz-backend`, copiez `.env.example` vers `.env`, puis remplacez
les trois valeurs `replace-with-...`. `JWT_SECRET` et `TOTP_ENCRYPTION_KEY`
doivent être distincts et contenir au moins 32 caractères ;
`ADMIN_PASSWORD` doit en contenir au moins 16.

```shell
uv sync
uv run fastapi dev main.py
```

L’API écoute sur `http://localhost:8000`. Sa documentation interactive est
disponible sur `http://localhost:8000/docs` en développement.

### 2. Frontend

Dans un second terminal, depuis `open-quiz-frontend` :

```shell
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

Ouvrez `http://localhost:5173`. Vite transmet automatiquement les requêtes
`/api` au backend local.

### Vérifications

```shell
cd open-quiz-backend
uv run ruff check .
uv run pytest -q
```

```shell
cd open-quiz-frontend
pnpm lint
pnpm typecheck
pnpm build
```

## Mise en production

Le déploiement fourni utilise deux conteneurs non privilégiés et un volume
Docker persistant pour SQLite. Le frontend écoute uniquement sur
`127.0.0.1:7800` : placez-le derrière un reverse proxy HTTPS sur l’hôte.

### 1. Configuration

Copiez le modèle de production sans remplacer votre éventuel fichier existant :

```shell
cp open-quiz-backend/.env.production.example open-quiz-backend/.env
```

Définissez ensuite :

- `FRONTEND_ORIGIN` avec l’origine HTTPS publique exacte, sans chemin ;
- deux secrets aléatoires distincts d’au moins 32 caractères pour
  `JWT_SECRET` et `TOTP_ENCRYPTION_KEY` ;
- un mot de passe administrateur unique d’au moins 16 caractères.

Ne placez jamais `.env` dans Git. Sauvegardez `TOTP_ENCRYPTION_KEY` dans un
gestionnaire de secrets : sa perte impose la réinitialisation de toutes les
inscriptions 2FA.

Exemple de reverse proxy Caddy installé sur l’hôte :

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

Le DNS doit pointer vers le serveur et les ports 80/443 doivent être ouverts.
Le port 7800 doit rester lié à l’interface locale.

### 2. Démarrage et vérification

```shell
docker compose config --quiet
docker compose up --detach --build --remove-orphans
docker compose ps
```

Attendez que les deux services soient `healthy`, puis vérifiez depuis
l’extérieur :

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est `{"status":"ok"}`. Vérifiez également la connexion
administrateur, la création d’une classe et un quiz de test complet avant
l’ouverture aux utilisateurs.

### 3. Mises à jour

Depuis la racine du dépôt :

```powershell
.\update.ps1
```

```shell
sh ./update.sh
```

Les scripts n’acceptent qu’une mise à jour Git en avance rapide, reconstruisent
les images, recréent les conteneurs et affichent leur état.

Après chaque mise à jour, contrôlez `docker compose ps`, le point de santé et
les journaux. Les journaux Docker sont limités à cinq fichiers de 10 Mo par
service.

## Exploitation et sauvegardes

- Surveillez `/api/health`, l’espace disque du volume et l’expiration du
  certificat TLS.
- Sauvegardez régulièrement le volume `open-quiz-data`. SQLite utilise WAL :
  effectuez la copie avec un outil compatible SQLite ou pendant un arrêt
  contrôlé des conteneurs.
- Centralisez les événements JSON `security.*`, `auth.login_rate_limited` et
  `auth.refresh_reuse_detected`.
- Créez un tag Git pour chaque version déployée afin de pouvoir reconstruire
  exactement la version précédente.

## Licence

Ce projet est distribué sous la licence MIT. Voir [LICENSE](LICENSE).
