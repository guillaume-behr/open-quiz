# Open Quiz Frontend

Interface React 19 et TypeScript de l’application Open Quiz.

## Démarrage

Le backend doit être accessible sur `http://localhost:8000`.

```shell
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

L’interface est ensuite disponible sur `http://localhost:5173`. Le proxy Vite
transmet `/api` au backend.

## Vérifications

```shell
pnpm lint
pnpm format:check
pnpm test
pnpm typecheck
pnpm build
```

La compilation de production est écrite dans `dist`.
`pnpm test` vérifie que les huit catalogues de traduction possèdent les mêmes
clés et variables d’interpolation.

`VITE_API_URL` peut définir une origine d’API absolue lorsque le proxy Vite
n’est pas utilisé. Laissez-la vide pour le développement et le déploiement
Caddy fournis.

## Architecture

- `src/api` centralise les appels HTTP et la rotation de session ;
- `src/pages` contient les espaces public, enseignant et administrateur ;
- `src/components` regroupe les fonctions métier et les composants d’interface ;
- `public/locales` contient les traductions française, anglaise, allemande,
  espagnole, portugaise, ukrainienne, arabe et chinoise simplifiée ;
- `public/pyodide` fournit le runtime Python utilisé entièrement dans le
  navigateur.

Les pages sont chargées à la demande. Les extraits Python s’exécutent dans un
Web Worker isolé et sont interrompus après dix secondes afin qu’un programme
bloqué ne fige pas l’interface.

## Traduction des quiz

Le frontend compare la langue d’origine fournie par la session de quiz à la
langue d’interface résolue par i18next. En cas de différence, il propose à
l’élève d’activer une traduction automatique avec un avertissement sur les
erreurs possibles. Le titre, les questions et les choix sont traduits ; les
blocs de code restent inchangés. Le texte original peut être rétabli sans
quitter la session.

La traduction repose sur l’API expérimentale `Translator` du navigateur. Elle
est déclenchée uniquement par le bouton de l’élève et s’exécute localement. Le
navigateur peut télécharger un modèle lors de la première demande. En l’absence
de prise en charge du navigateur ou de la paire de langues, le frontend affiche
le message localisé `automatic-translation-unavailable` et conserve le contenu
original. Aucun fournisseur de traduction distant ni aucune clé d’API ne sont
nécessaires.

Les textes de l’encart, du bouton, de la progression et des erreurs sont stockés
dans les huit catalogues de `public/locales`, comme le reste de l’interface.

## Production

Le `Dockerfile` compile les ressources avec Node.js puis les sert avec Caddy.
Caddy applique les en-têtes de sécurité, sert l’application monopage et transmet
`/api` au service backend. Le déploiement normal se fait avec le
`docker-compose.yml` situé à la racine du dépôt.
