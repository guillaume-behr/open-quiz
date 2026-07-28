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
pnpm typecheck
pnpm build
```

La compilation de production est écrite dans `dist`.

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

## Production

Le `Dockerfile` compile les ressources avec Node.js puis les sert avec Caddy.
Caddy applique les en-têtes de sécurité, sert l’application monopage et transmet
`/api` au service backend. Le déploiement normal se fait avec le
`docker-compose.yml` situé à la racine du dépôt.
