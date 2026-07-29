# Contribuer à Open Quiz

Merci de contribuer à Open Quiz. Les corrections ciblées, tests, traductions et
améliorations de documentation sont les bienvenues.

## Avant de commencer

- recherchez les issues et pull requests existantes ;
- ouvrez une issue pour une évolution importante ou un changement de
  comportement ;
- ne publiez jamais de secret, de donnée d’élève ni de rapport de vulnérabilité
  dans une issue publique ; utilisez la procédure de `SECURITY.md`.

## Environnement

Suivez l’installation du `README.md`, puis créez une branche courte depuis la
branche par défaut :

```shell
git switch -c type/description-courte
```

Préfixes suggérés : `fix/`, `feat/`, `docs/`, `test/` ou `chore/`.

## Principes de contribution

- préservez les interfaces existantes sauf nécessité documentée ;
- gardez les règles métier et les autorisations côté backend ;
- ajoutez un test ciblé pour chaque correction de comportement ;
- ne modifiez pas les fichiers de verrouillage sans changement de dépendance ;
- ne modifiez pas les ressources vendoriées de `public/pyodide` sans expliquer
  leur provenance et leur mise à jour ;
- ajoutez toute chaîne visible aux huit catalogues de traduction ;
- privilégiez un changement lisible et limité à une refonte générale.

## Vérifications requises

Backend :

```shell
cd open-quiz-backend
uv sync --frozen --dev
uv run ruff check app tests main.py scripts
uv run ruff format --check app tests main.py scripts
uv run pytest -q
```

Frontend :

```shell
cd open-quiz-frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check
pnpm test
pnpm typecheck
pnpm build
```

Pour une modification du déploiement :

```shell
docker compose config --quiet
docker compose build
```

## Pull requests

Une pull request doit expliquer le problème, la solution, les risques et les
vérifications réellement exécutées. Ajoutez des captures uniquement lorsqu’un
changement visuel en bénéficie. Gardez les commits compréhensibles ; le projet
accepte les messages de type Conventional Commits sans les imposer.

En contribuant, vous acceptez que votre contribution soit distribuée sous la
licence MIT du projet.
