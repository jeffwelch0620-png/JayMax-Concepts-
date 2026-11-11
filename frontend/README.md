# Inventory web app

React app built with [Vite](https://vite.dev). Since 2026-11-11 it no longer uses Create React App or craco.

| Command | What it does |
|---|---|
| `yarn start` | Dev server on http://localhost:3000 |
| `yarn build` | Production build into `build/`, which Render publishes |
| `yarn test` | Unit tests (Jest, jsdom) |
| `yarn lint` | ESLint; CI runs it with `--max-warnings 0` |
| `yarn check:colors` | Raw-colour allowance check |

Settings are read as `process.env.REACT_APP_*` (from Render or a local `.env`) and fixed into the bundle at build time. The `@/` import prefix points to `src/`.
