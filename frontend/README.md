# Valence OS frontend

React/Vite client for Valence OS. Project-level setup, architecture, scope, and trust boundaries live in the repository-root `README.md` and `CLAUDE.md`; this file only records frontend-specific commands.

```bash
npm install
npm run dev      # http://localhost:5173; proxies /api to FastAPI on :8000
npm run build    # writes dist/, served by FastAPI in the one-process setup
npm run lint
```

Presentation changes follow the root `DESIGN-GUIDE.md`. Reuse `src/ui.jsx`, `src/tokens.css`, existing status treatments, and the four-destination information architecture before introducing new primitives.
