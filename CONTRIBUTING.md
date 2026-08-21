# Contribuer à Open Quiz

Merci de votre intérêt pour Open Quiz. Les corrections ciblées, tests,
traductions et améliorations de documentation sont les bienvenues.

## Avant de commencer

1. consultez les
   [issues ouvertes](https://github.com/guillaume-behr/open-quiz/issues) et les
   [pull requests](https://github.com/guillaume-behr/open-quiz/pulls) ;
2. ouvrez une issue avant une évolution importante, une transition de données
   ou un changement de comportement public ;
3. préparez l’[environnement de développement](README.md#développement-local) ;
4. ne publiez jamais de secret, de donnée d’élève ou de vulnérabilité : utilisez
   la procédure privée de [SECURITY.md](SECURITY.md).

Une petite correction évidente peut être proposée directement. Pour une
fonctionnalité, décrivez d’abord le besoin utilisateur et les contraintes afin
d’éviter un travail incompatible avec la direction du projet.

## Préparer une branche

Créez une branche courte depuis la branche par défaut à jour :

```shell
git switch master
git pull --ff-only
git switch -c type/description-courte
```

Préfixes suggérés : `fix/`, `feat/`, `docs/`, `test/`, `refactor/` ou `chore/`.

## Principes de contribution

- limitez chaque pull request à un problème cohérent ;
- conservez les interfaces existantes, sauf changement discuté et documenté ;
- gardez les règles métier et les autorisations côté backend ;
- ajoutez un test ciblé pour toute correction de comportement ;
- ne modifiez les fichiers de verrouillage que lorsqu’une dépendance change ;
- ne modifiez pas `public/pyodide` sans documenter la provenance et la procédure
  de mise à jour ;
- ne mélangez jamais données réelles et jeux de test ;
- utilisez des messages de commit compréhensibles. Conventional Commits est
  accepté sans être obligatoire.

## Selon la nature du changement

### API, données et sécurité

- validez les entrées côté backend, même si le frontend les contrôle déjà ;
- vérifiez les permissions avec les rôles administrateur, enseignant et élève ;
- préservez l’atomicité des imports et opérations concurrentes ;
- accompagnez toute évolution du schéma PostgreSQL d’une stratégie explicite
  de déploiement et des tests correspondants ;
- documentez les changements d’API, de configuration, de conservation ou de
  sécurité ;
- ajoutez une entrée à [CHANGELOG.md](CHANGELOG.md) pour tout changement visible
  ou incompatible.

### Interface et accessibilité

- utilisez les composants et styles déjà présents ;
- conservez la navigation au clavier, les libellés accessibles, les états de
  focus et la réduction des animations ;
- vérifiez au minimum les tailles mobile et bureau ;
- ajoutez une capture à la pull request lorsqu’elle facilite la revue ;
- exécutez les tests Playwright lorsque le parcours utilisateur change.

### Traductions

Toute nouvelle chaîne visible doit exister dans les huit catalogues de
`open-quiz-frontend/public/locales`.

- l’anglais est la référence structurelle des clés ;
- conservez exactement les variables `{{...}}` et les suffixes de pluriel ;
- exécutez `pnpm test` pour contrôler les catalogues ;
- pour ajouter une langue, suivez la section internationalisation du
  [README frontend](open-quiz-frontend/README.md#internationalisation).

### Documentation

- utilisez des chemins et commandes réellement présents dans le dépôt ;
- évitez de dupliquer les détails d’exploitation dans plusieurs fichiers ;
- vérifiez les liens relatifs et les ancres ;
- mettez à jour le changelog si la documentation accompagne une évolution
  visible.

## Vérifications

Exécutez les contrôles correspondant aux fichiers modifiés. La CI fait autorité
pour les contrôles obligatoires. Chaque bloc ci-dessous part de la racine du
dépôt ; revenez-y avant de passer à un autre composant.

### Backend

```shell
cd open-quiz-backend
uv sync --frozen --dev
uv run --frozen ruff check app tests main.py scripts
uv run --frozen ruff check --select S app main.py scripts
uv run --frozen ruff format --check app tests main.py scripts
uv run --frozen pytest -q
uv run --frozen pip-audit
```

### Frontend

```shell
cd open-quiz-frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check
pnpm test
pnpm typecheck
pnpm build
pnpm audit --audit-level low
```

Pour un parcours utilisateur ou une modification du proxy HTTP/WebSocket :

```shell
pnpm exec playwright install chromium
pnpm test:e2e
```

### Conteneurs et déploiement

Après une modification de Docker, Caddy, Compose ou des variables de
production :

```shell
test -f open-quiz-backend/.env || \
    cp open-quiz-backend/.env.production.example open-quiz-backend/.env
docker compose config --quiet
docker compose build
```

N’utilisez ces valeurs d’exemple que pour valider la structure. Une instance
réelle exige des secrets robustes et distincts.

## Ouvrir une pull request

Avant l’envoi :

- relisez le diff complet et retirez les changements sans rapport ;
- vérifiez qu’aucun secret, fichier `.env`, jeton ou donnée personnelle n’est
  présent ;
- décrivez le problème, la solution, les risques et les compromis ;
- indiquez les commandes réellement exécutées et leur résultat ;
- mentionnez les tests ajoutés, les évolutions de schéma et les changements de
  documentation ;
- liez l’issue avec `Closes #…` lorsqu’elle doit être fermée à la fusion.

Une revue peut demander de réduire le périmètre, d’ajouter un test ou de
documenter une décision. Les échanges doivent rester factuels et respectueux.

En contribuant, vous acceptez que votre contribution soit distribuée sous la
[licence MIT](LICENSE) du projet.
