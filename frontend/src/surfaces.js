/**
 * Stage 17 — the client half of the surface registry (`SURFACE-USAGE-SPEC.md` §4).
 *
 * `backend/app/surfaces.py` is the authority. This file mirrors the three fields the `<Surface>`
 * wrapper needs at render time — `route`, `kind`, `label` — and nothing else. It is a mirror for the
 * same reason `EVENT_NAMES` is: a typo at a call site should fail here, immediately, rather than be
 * rejected by a server that has been told to ignore what it does not recognise. The drift test
 * `test_surface_registry.py::test_the_client_registry_matches_the_server` fails if the two disagree
 * on the key set or on any mirrored field.
 *
 * What is deliberately **not** here: `reaches`, `provides`, `explains_refusal`, `cadence`, and the
 * window lengths. Those are what §7.7's safety check and §6's four axes are computed from, and a
 * client copy of them would be a second place a retirement could be judged safe. The client asks the
 * server; the server answers with the reason.
 *
 * `label` is here and never in an event payload. It is the human string, so it travels to a screen
 * and nowhere else — `SENSITIVE_KEYS` on the server blocks the key outright.
 */

/** key → { route, kind, label }. Mirrors `surfaces.REGISTRY`. */
export const SURFACES = Object.freeze({
  "today.queue": { route: "today", kind: "section", label: "Attention queue" },
  "today.absence": { route: "today", kind: "section", label: "Where you are not looking" },
  "today.saved_views": { route: "today", kind: "section", label: "Saved views" },

  "accounts.book": { route: "accounts", kind: "section", label: "Account book" },
  "accounts.portfolio_analytics": { route: "accounts", kind: "panel", label: "Portfolio analytics" },

  "overview.account_path": { route: "account.overview", kind: "section", label: "Next best move" },
  "overview.intake_drop": { route: "account.overview", kind: "section", label: "Drop a document" },
  "overview.readiness_summary": { route: "account.overview", kind: "section", label: "Relationship readiness" },
  "overview.next_on_account": { route: "account.overview", kind: "section", label: "Next on account" },
  "overview.current_point_of_view": { route: "account.overview", kind: "section", label: "Current point of view" },
  "overview.since_last_visit": { route: "account.overview", kind: "section", label: "Since last visit" },
  "overview.where_account_stands": { route: "account.overview", kind: "section", label: "Where the account stands" },
  "overview.what_moved": { route: "account.overview", kind: "section", label: "What moved" },
  "overview.what_is_stuck": { route: "account.overview", kind: "section", label: "What is stuck" },

  "ledger.records": { route: "account.ledger", kind: "section", label: "Records ledger" },
  "ledger.activity": { route: "account.ledger", kind: "section", label: "Activity timeline" },
  "ledger.communications": { route: "account.ledger", kind: "section", label: "Communications" },
  "ledger.extraction": { route: "account.ledger", kind: "section", label: "Extract from a transcript" },

  "people.stakeholder_map": { route: "account.people", kind: "section", label: "Stakeholder map" },
  "people.champions": { route: "account.people", kind: "section", label: "Champions" },
  "people.person_card": { route: "account.people", kind: "panel", label: "Person card" },
  "people.influence": { route: "account.people", kind: "section", label: "Influence and relationships" },
  "people.exec_alignment": { route: "account.people", kind: "section", label: "Executive alignment" },
  "people.org_changes": { route: "account.people", kind: "section", label: "Org changes" },
  "people.messaging": { route: "account.people", kind: "section", label: "Messaging" },

  "plan.timeline": { route: "account.plan", kind: "section", label: "Launch timeline" },
  "plan.requirement_detail": { route: "account.plan", kind: "panel", label: "Requirement detail" },
  "plan.checklists": { route: "account.plan", kind: "section", label: "Checklists" },
  "plan.calendar": { route: "account.plan", kind: "section", label: "Calendar" },
  "plan.adoption_comms": { route: "account.plan", kind: "section", label: "Communication sequences" },
  "plan.campaigns": { route: "account.plan", kind: "section", label: "Adoption campaigns" },
  "plan.program_detail": { route: "account.plan", kind: "panel", label: "Program detail" },

  "commercial.whitespace": { route: "account.commercial", kind: "section", label: "Whitespace" },
  "commercial.value_ledger": { route: "account.commercial", kind: "section", label: "Value ledger" },
  "commercial.funding": { route: "account.commercial", kind: "section", label: "Funding" },
  "commercial.signals": { route: "account.commercial", kind: "section", label: "Expansion signals" },
  "commercial.company_intel": { route: "account.commercial", kind: "section", label: "Company intel" },
  "commercial.growth": { route: "account.commercial", kind: "section", label: "Growth and renewal" },
  "commercial.pipeline": { route: "account.commercial", kind: "section", label: "Expansion pipeline" },

  "evidence.value_library": { route: "account.evidence", kind: "section", label: "Value library" },
  "evidence.metrics": { route: "account.evidence", kind: "section", label: "Metrics and benchmarks" },

  "outputs.artifacts": { route: "account.outputs", kind: "section", label: "Artifacts" },
  "outputs.qbr": { route: "account.outputs", kind: "section", label: "QBR pack" },
  "outputs.team_update": { route: "account.outputs", kind: "section", label: "Team update" },
  "outputs.mutual_action_plan": { route: "account.outputs", kind: "section", label: "Mutual action plan" },

  "internal.forecast": { route: "account.internal", kind: "section", label: "Forecast" },
  "internal.asks": { route: "account.internal", kind: "section", label: "Asks and escalations" },
  "internal.reviews": { route: "account.internal", kind: "section", label: "Leadership reviews" },
  "internal.coverage": { route: "account.internal", kind: "section", label: "Coverage" },

  "library.sources": { route: "library", kind: "section", label: "Files and context" },
  "library.playbooks": { route: "library", kind: "section", label: "Playbook library" },

  "coach.home": { route: "coach", kind: "section", label: "Coaching focus" },
  "coach.intake": { route: "coach", kind: "section", label: "Review a call" },
  "coach.review": { route: "coach", kind: "section", label: "Coaching review" },
  "coach.practice": { route: "coach", kind: "section", label: "Targeted practice" },
  "coach.history": { route: "coach", kind: "section", label: "Coaching history" },

  "global.copilot": { route: "global", kind: "panel", label: "Account copilot" },

  "operations.measurement": { route: "operations", kind: "section", label: "Product measurement" },
  "operations.surface_usage": { route: "operations", kind: "section", label: "Surface usage" },
  "operations.copilot_governance": { route: "operations", kind: "section", label: "Copilot governance" },

  "command.log_interaction": { route: "global", kind: "command", label: "Log interaction" },
  "command.export_team_update": { route: "account.outputs", kind: "command", label: "Export team update" },
  "command.start_plan": { route: "account.plan", kind: "command", label: "Start a plan from a playbook" },
  "command.review_call": { route: "coach", kind: "command", label: "Start private call review" },
});

export const SURFACE_KEYS = Object.freeze(Object.keys(SURFACES));

/** §5's two vocabularies, kept apart here so no call site has to remember which property to use. */
export const isCommand = (key) => SURFACES[key]?.kind === "command";
export const isSurface = (key) => Boolean(SURFACES[key]) && !isCommand(key);

export function surfaceMeta(key) {
  return SURFACES[key] || null;
}

/**
 * The `surface_rendered` payload for one key. Returns `null` for an unregistered key rather than
 * inventing a row: the tracker would drop it anyway, and returning a half-formed payload would let
 * a caller send a render event with no surface on it.
 */
export function renderProperties(key, { renderReason = "navigation", position = null } = {}) {
  const meta = SURFACES[key];
  if (!meta || meta.kind === "command") return null;
  return {
    surface: key,
    route: meta.route,
    kind: meta.kind,
    render_reason: renderReason,
    position: typeof position === "number" && position >= 0 ? position : null,
  };
}

/** The `surface_engaged` payload. `engagement` is §5's closed six; the server rejects anything else. */
export function engagementProperties(key, engagement) {
  const meta = SURFACES[key];
  if (!meta || meta.kind === "command") return null;
  return { surface: key, route: meta.route, kind: meta.kind, engagement };
}

export function dismissProperties(key, dismissKind) {
  const meta = SURFACES[key];
  if (!meta || meta.kind === "command") return null;
  return { surface: key, route: meta.route, dismiss_kind: dismissKind };
}

/**
 * The route string for a navigation state, in the registry's own vocabulary.
 *
 * Derived from `nav` rather than from `window.location`, so the value can only ever be one of the
 * strings this repo authored. A URL can carry a record id, a saved-view id, a search term — reading
 * the path into a measurement property is how an account name reaches the sink through a route
 * field nobody thought of as content.
 */
export function routeForNav(nav) {
  if (!nav || !nav.dest) return null;
  if (nav.dest !== "account") return nav.dest;
  return `account.${nav.tab || "overview"}`;
}

/** `navigation_landed`. `route` is derived; nothing here reads the URL. */
export function navigationProperties(nav, { entryPoint = "navigation", isFirstOfSession = false } = {}) {
  const route = routeForNav(nav);
  if (!route) return null;
  return { route, entry_point: entryPoint, is_first_of_session: Boolean(isFirstOfSession) };
}

export function commandProperties(key, entryPoint) {
  const meta = SURFACES[key];
  if (!meta || meta.kind !== "command") return null;
  return { command: key, route: meta.route, entry_point: entryPoint };
}
