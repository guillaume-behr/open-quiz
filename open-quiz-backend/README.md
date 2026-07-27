# Open Quiz Backend

## Technologies utilisées

- Python 3.14 ou supérieur
- FastAPI avec ses dépendances standard
- SQLAlchemy avec SQLite
- Authentification JWT et mots de passe hachés avec Argon2
- uv pour la gestion de l'environnement, des dépendances et du verrouillage des versions

## Démarrage

Copiez `.env.example` vers `.env`, puis renseignez un secret JWT aléatoire d'au
moins 32 caractères et un mot de passe administrateur robuste. Le compte
administrateur est créé au premier démarrage. Ensuite, ses droits, son état et
son mot de passe restent synchronisés avec `.env` à chaque démarrage.

```shell
uv run fastapi dev main.py
```

La documentation interactive est disponible sur `http://localhost:8000/docs`.

Les jetons d'accès expirent rapidement et restent uniquement en mémoire dans le
navigateur. Les sessions longues utilisent un cookie HttpOnly rotatif et
révocable. Pour révoquer les secrets locaux et en générer de nouveaux sans les
afficher dans le terminal :

```shell
uv run python scripts/rotate_local_secrets.py
```

En production, utilisez `APP_ENV=production` et une origine frontend HTTPS.
Les cookies deviennent alors automatiquement sécurisés, la documentation
interactive est désactivée et les requêtes HTTP sont redirigées vers HTTPS.
Placez également une limitation de débit au niveau du reverse proxy en
complément de celle de l'application, notamment si plusieurs processus backend
sont exécutés.
