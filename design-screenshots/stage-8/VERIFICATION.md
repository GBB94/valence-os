# Stage 8 verification

Stage 8 adds one rendered change: Operations now shows the complete connection registry and gate
state instead of a three-row mock-adapter subset. The rest of the slice is governance, integration,
and executable proof rather than a new account-workspace surface.

## Automated verification

- Backend: **220 passed** (`.venv/bin/python -m pytest`).
- Frontend: production Vite build passed.
- Clean seed: migrations applied through `0024_stage8_integration_hardening.sql`.
- Clean database: `PRAGMA foreign_key_check` returned no rows.
- Stage 8 test creates a brand-new synthetic account and reaches a reviewed, recorded-as-sent
  expansion business case using only mock/local adapters.
- Registry test asserts all eleven runtime boundaries appear in `CONNECTIONS.md`, fixture paths
  exist, Operations exposes the same IDs, and every default gate state is local.
- Real-mode test asserts API LLM selection is rejected without both approval values.

## Visual verification

The in-app browser was unavailable (`agent.browsers.list()` returned no browser instances), so no
honest light/dark screenshots could be captured. Per the browser-control instructions, no unrelated
browser backend was substituted. Static review confirms the Operations change uses the existing
semantic table, badge, token, and status-label conventions; the production build confirms the JSX.

Recapture when the in-app browser is available:

1. Seed and run the app, then open Operations at desktop width.
2. Capture the Connection registry in light and dark themes.
3. Verify all eleven rows, the local gate labels, readable long fixture/config text, keyboard focus,
   and split-screen behavior near 900px.

