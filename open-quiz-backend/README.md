# Open Quiz Backend

## Technologies utilisées

- Python 3.14 ou supérieur
- FastAPI avec ses dépendances standard
- SQLAlchemy avec SQLite
- Authentification JWT et mots de passe hachés avec Argon2
- uv pour la gestion de l'environnement, des dépendances et du verrouillage des versions

## Démarrage

Copiez `.env.example` vers `.env`, puis renseignez deux secrets aléatoires
distincts d'au moins 32 caractères pour les jetons JWT et le chiffrement TOTP,
ainsi qu'un mot de passe administrateur robuste. Le compte administrateur est
créé au premier démarrage. Son identifiant interne est ensuite enregistré comme
état de sécurité : modifier `ADMIN_USERNAME` renomme ce même compte au lieu de
créer un second administrateur. Ses droits, son état et son mot de passe restent
synchronisés avec `.env`.

```shell
uv run fastapi dev main.py
```

La documentation interactive est disponible sur `http://localhost:8000/docs`.

Les jetons d'accès expirent rapidement et restent uniquement en mémoire dans le
navigateur. Les sessions longues utilisent un cookie HttpOnly rotatif et
révocable. La réutilisation d'un ancien jeton révoque toute sa famille de
sessions. Un changement de mot de passe administrateur révoque ses sessions et
un changement de `JWT_SECRET` révoque toutes les sessions. Tous les comptes
doivent configurer une application
d'authentification TOTP lors de leur première connexion. Les secrets TOTP sont
chiffrés dans SQLite avec `TOTP_ENCRYPTION_KEY`. Sauvegardez cette clé : si elle
est perdue ou remplacée, chaque utilisateur devra réinitialiser son inscription
2FA.

Si un utilisateur perd son authentificateur, réinitialisez son inscription 2FA
et révoquez ses sessions actives avec :

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

La limitation d'authentification est stockée en base de données et fonctionne
donc avec plusieurs processus. `LOGIN_ATTEMPTS` limite une adresse IP tandis que
`LOGIN_ACCOUNT_ATTEMPTS`, volontairement plus élevé, protège un compte contre
une attaque distribuée. Configurez le reverse proxy comme seule entrée vers le
backend et n'acceptez les en-têtes `Forwarded` que de ce proxy. Le conteneur
fourni respecte cette contrainte grâce au réseau Docker interne.

`MAX_REQUEST_BODY_BYTES` limite la taille des requêtes applicatives. Le
conteneur Uvicorn ajoute également une limite de concurrence et des délais de
connexion courts. Conservez des limites équivalentes sur le reverse proxy
externe.

Les événements de sécurité sont émis en JSON sur la sortie standard avec un
horodatage UTC. En production, envoyez-les vers un collecteur central en
écriture seule pour l'application, avec contrôle d'accès, alertes et politique
de rétention. Alertez notamment sur `auth.refresh_reuse_detected`,
`auth.login_rate_limited` et les événements `security.*`.

Le fichier Compose situé dans `open-quiz-frontend` démarre le backend sur un
réseau interne, conserve SQLite dans un volume dédié et fait passer `/api` par
Caddy. L'origine publique configurée dans `FRONTEND_ORIGIN` doit correspondre
exactement à l'adresse utilisée par le navigateur.
