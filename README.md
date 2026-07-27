# Open Quiz

## Docker

Chaque application possède son propre `Dockerfile` :

- `open-quiz-frontend/Dockerfile`
- `open-quiz-backend/Dockerfile`

Après avoir configuré `open-quiz-backend/.env`, démarrez l’ensemble depuis la
racine du dépôt :

```shell
docker compose up --build
```

## Mise à jour

`docker compose restart` ne reconstruit pas les images après un `git pull`.
Utilisez le script adapté à votre système depuis la racine du dépôt :

```powershell
.\update.ps1
```

```shell
sh ./update.sh
```

Les scripts récupèrent uniquement une mise à jour Git en avance rapide,
reconstruisent les images modifiées, recréent les conteneurs et affichent leur
état. Les données SQLite restent stockées dans le volume Docker
`open-quiz-data`.

La commande équivalente sans script est :

```shell
git pull --ff-only && docker compose up --detach --build --remove-orphans
```
