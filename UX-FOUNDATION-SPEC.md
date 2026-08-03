# Valence OS UX foundation specification

**Status:** Release 1 and Release 2 Slices 2.0–2.2 implemented; later Release 2 slices detailed in `ACCOUNT-COMMAND-CENTER-SPEC.md`; Release 3 directional, 2026-08-03
**Authority:** Additive to `DESIGN-GUIDE.md`; trust and data boundaries in `CLAUDE.md` remain unchanged.  
**Scope:** Navigation, reusable portfolio views, account orientation, and the migration path toward a decision-oriented workspace.

## 1. Why this exists

Valence has strong individual modules but no shared orchestration layer. The current React shell keeps navigation only in memory, list surfaces expose one fixed arrangement, and the account workspace has accumulated eight tabs plus many nested surfaces. The visual system is not the problem. The next phase must make the existing product addressable and adaptable before changing its module taxonomy.

This specification therefore separates low-regret foundations from later product-model changes. Release 1 improves navigation and repeat work without renaming, removing, or moving an existing module. Later releases may consolidate the workspace only after the foundation produces real usage evidence.

## 2. Outcomes

An operator can:

1. Refresh, bookmark, share, and use Back/Forward without losing the current destination, account, workspace tab, or program scope.
2. Return to a useful portfolio list arrangement without rebuilding its filters.
3. Inspect an account or record from a list without unnecessarily losing list context.
4. Open an account and understand what changed, what needs a decision, and what happens next.
5. Read internal activity, customer activity, external change, and future events on one time axis.

## 3. Non-goals for Release 1

- Replacing the eight account tabs with the proposed five-job architecture.
- Adding customer-facing authentication or a shared portal.
- Adding multi-user permissions, mentions, or assignment semantics.
- Introducing objectives, milestones, hierarchy, or unified-event database tables.
- Connecting a real external data source.
- Changing any evidence, promotion, privacy, or client-output boundary.

## 4. Target information architecture

The likely long-term account workspace is:

- **Summary** — change since last review, decisions, objectives, next meeting, renewal, stakeholder gaps, and the current growth thesis.
- **Activity** — internal, customer, external, and planned events on one filterable chronology.
- **Relationships** — stakeholder map, table, coverage, influence, and engagement recency.
- **Outcomes** — customer objective → milestone → task/intervention → evidence.
- **Growth** — whitespace, value, funding, pipeline, company signals, and the joined expansion thesis.

Evidence remains a cross-cutting provenance layer; Outputs remains contextual creation plus a document library; Internal becomes a role-specific review workspace. This target is directional, not authorization to move the current tabs in Release 1.

## 5. Release plan

### Release 1 — addressability and repeat work

#### 5.1 Canonical navigation

Canonical routes:

| Destination | Route |
|---|---|
| Today | `/today` |
| Accounts | `/accounts` |
| Account overview | `/accounts/:accountId/overview` |
| Account workspace tab | `/accounts/:accountId/:tab` |
| Program-scoped workspace tab | `/accounts/:accountId/:tab?program=:programId` |
| Library | `/library` |
| Operations | `/operations` |

Rules:

- `/` normalizes to `/today` with `replaceState`.
- Unknown destinations and invalid workspace tabs normalize to `/today`.
- A syntactically valid account route whose account does not exist normalizes to `/accounts` after the account list loads.
- In-app navigation uses `pushState`; normalization uses `replaceState`.
- `popstate` restores the complete navigation state without adding a new history entry.
- Re-selecting the current route does not add a duplicate history entry.
- The production server returns the SPA entry point for extensionless, non-API routes; missing assets and unknown API routes remain 404s.
- No third-party router is required for this bounded route contract.

#### 5.2 Saved portfolio views

The first saved-view surfaces are Today and the Accounts Book.

- Built-in views remain available and cannot be deleted.
- The operator can save the current filter arrangement under a name, select it later, and delete custom views.
- A saved view stores presentation state only: query, grouping/filter selections, and sort. It never stores or copies account records.
- Custom views are browser-local preferences in Release 1, matching theme, density, and rail state. This is deliberate for the current single-editor product; a future team release may migrate the same JSON contract behind an API.
- Selecting a built-in or saved view is addressable by a `view` query parameter when possible. A custom view opened on a browser where it does not exist falls back visibly to the default view.
- Changing a filter after selecting a view marks the arrangement as modified; it does not silently overwrite the saved definition.
- Saving uses a non-blocking slide-over, never `window.prompt()`.

Initial built-in Today views:

- All attention
- Needs you now
- This week
- Keep an eye

Initial built-in Accounts views:

- All accounts
- Needs attention
- Commercial risk
- Delivery risk

#### 5.3 List context and preview contract

Release 1 defines the reusable contract even if only the first account preview lands:

- Clicking a row's primary label may open a preview; an explicit “Open account” action performs full navigation.
- Preview supports Escape, focus containment, focus restoration, and a stable full-record link.
- Compact preview, standard inspector, and wide authoring are distinct width modes. The existing standard 480px slide-over remains valid; it is no longer the only mode.
- Preview content begins with decisions and next actions, then supporting detail.

### Release 2 — account command center and unified activity

- Replace the current Overview body with one command center that can switch among Operate, Prepare, and Leadership lenses. Operate is the default; all lenses use the same source contracts rather than becoming separate dashboards.
- Add “since last visit” and “since last review” change summaries.
- Normalize existing interactions, ledger records, communications, company events, assessment changes, internal reviews, and planned events into one read model before deciding whether a new persisted event table is necessary.
- Add purpose-specific Copilot entry points for meeting preparation, renewal review, handoff, and change review.
- `ACCOUNT-COMMAND-CENTER-SPEC.md` contains the detailed proposed implementation contract for this release, including temporal semantics, source coverage, checkpoints, URL state, accessibility, and delivery slices.

### Release 3 — outcomes and growth synthesis

- Add customer objective → milestone → task/intervention → evidence.
- Add first-class account/corporate hierarchy and roll-up scope.
- Build the Growth Thesis across whitespace, value, funding, people, external signals, and pipeline.
- Reassess the five-job account navigation using observed Release 1–2 usage.

## 6. Acceptance criteria for Release 1

### Navigation

- Direct loading of every canonical route renders the correct destination.
- Refresh preserves account, tab, and program scope.
- Back and Forward traverse prior Valence destinations in order.
- Search, command palette, rail, breadcrumb, account tabs, and program selector all write canonical URLs.
- Invalid tabs and missing accounts recover without a blank or permanent loading state.
- Built frontend deep links work through FastAPI.

### Saved views

- Today and Accounts expose built-in view choices plus named custom views.
- Query/filter changes immediately update the visible rows and indicate a modified view.
- Saving and deleting custom views persist across reloads.
- Missing/corrupt local preference data fails closed to built-ins.
- Saved-view controls are keyboard operable and meet both-theme contrast requirements.

### Regression and trust

- Capture remains globally available and preserves account/program prefill.
- No client-facing generator receives a new data source.
- No individual usage, sensitive person data, or real connection is introduced.
- Backend tests, frontend route tests, lint, and production build pass.
- Both themes receive a rendered verification when an in-app browser target is available; tooling unavailability is recorded rather than represented as a pass.

## 7. Later decisions deliberately deferred

These do not block Release 1:

- Final five-tab labels and the migration of Evidence, Outputs, and Internal.
- Whether team saved views are shared by default or explicitly published.
- Whether a measured scale problem eventually requires a rebuildable materialized index for the query-time unified activity projection.
- Objective visibility and the customer-sharing permission model.
- Corporate hierarchy semantics for legal entity, buying entity, business unit, and program.

## 8. Rollback and compatibility

- Existing screen components and API contracts remain intact in Release 1.
- Route parsing is centralized and pure, so the shell can fall back to `/today` without data migration.
- Saved views are additive preferences; deleting their local-storage key restores built-ins.
- No account export/import contract changes in Release 1.
