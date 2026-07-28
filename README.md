# Open Quiz

## Mise en production

Le déploiement fourni utilise deux conteneurs non privilégiés et un volume
Docker persistant pour SQLite. Le frontend écoute uniquement sur
`127.0.0.1:7800` : placez-le derrière un reverse proxy HTTPS sur l’hôte.

### 1. Configuration

Copiez le modèle de production sans remplacer votre éventuel fichier existant :

```shell
cp open-quiz-backend/.env.production.example open-quiz-backend/.env
```

Définissez ensuite :

- `FRONTEND_ORIGIN` avec l’origine HTTPS publique exacte, sans chemin ;
- deux secrets aléatoires distincts d’au moins 32 caractères pour
  `JWT_SECRET` et `TOTP_ENCRYPTION_KEY` ;
- un mot de passe administrateur unique d’au moins 16 caractères.

Ne placez jamais `.env` dans Git. Sauvegardez `TOTP_ENCRYPTION_KEY` dans un
gestionnaire de secrets : sa perte impose la réinitialisation de toutes les
inscriptions 2FA.

Exemple de reverse proxy Caddy installé sur l’hôte :

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
l’extérieur :

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

La réponse attendue est `{"status":"ok"}`. Vérifiez également la connexion
administrateur, la création d’une classe et un quiz de test complet avant
l’ouverture aux utilisateurs.

### 3. Sauvegardes

Les sauvegardes utilisent l’API de sauvegarde en ligne de SQLite, exécutent
`PRAGMA quick_check`, puis copient le fichier vérifié dans `backups/` :

```powershell
.\backup.ps1
```

```shell
sh ./backup.sh
```

Copiez régulièrement ce répertoire vers un stockage chiffré hors du serveur et
testez la restauration. Une sauvegarde conservée uniquement sur le serveur
n’est pas une protection contre sa perte.

Pour restaurer, arrêtez d’abord le backend, conservez une copie du volume
actuel, remplacez `/data/open-quiz.db` par une sauvegarde vérifiée dans le volume
`open-quiz-data`, supprimez les éventuels fichiers `open-quiz.db-wal` et
`open-quiz.db-shm`, puis redémarrez les services. Effectuez cette opération
pendant une fenêtre de maintenance.

### 4. Mises à jour

Depuis la racine du dépôt :

```powershell
.\update.ps1
```

```shell
sh ./update.sh
```

Lorsqu’un backend est déjà actif, les scripts créent d’abord une sauvegarde
vérifiée. Ils n’acceptent ensuite qu’une mise à jour Git en avance rapide,
reconstruisent les images, recréent les conteneurs et affichent leur état.

Après chaque mise à jour, contrôlez `docker compose ps`, le point de santé et
les journaux. Les journaux Docker sont limités à cinq fichiers de 10 Mo par
service.

## Exploitation

- Surveillez `/api/health`, l’espace disque du volume et l’expiration du
  certificat TLS.
- Centralisez les événements JSON `security.*`, `auth.login_rate_limited` et
  `auth.refresh_reuse_detected`.
- Conservez plusieurs générations de sauvegardes selon votre politique de
  rétention.
- Testez périodiquement une restauration sur un environnement isolé.
- Créez un tag Git pour chaque version déployée afin de pouvoir reconstruire
  exactement la version précédente.
