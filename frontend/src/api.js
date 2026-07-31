// Thin API client. In dev the backend runs on :8000; when served from dist it's same-origin.
const BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* keep default */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => req("GET", "/api/health"),
  search: (q) => req("GET", `/api/search?q=${encodeURIComponent(q)}`),
  library: ({ q = "", type = "", accountId = "", tag = "" } = {}) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q); if (type) p.set("type", type); if (accountId) p.set("account_id", accountId); if (tag) p.set("tag", tag);
    const qs = p.toString();
    return req("GET", `/api/library${qs ? "?" + qs : ""}`);
  },
  createSourceReference: (b) => req("POST", "/api/source-references", b),
  patchSourceReference: (id, b) => req("PATCH", `/api/source-references/${id}`, b),
  accounts: () => req("GET", "/api/accounts"),
  account: (id) => req("GET", `/api/accounts/${id}`),
  createAccount: (b) => req("POST", "/api/accounts", b),
  exportAccount: (id) => req("GET", `/api/accounts/${id}/export`),
  importAccount: (bundle) => req("POST", "/api/accounts/import", bundle),
  program: (id) => req("GET", `/api/programs/${id}`),
  createProgram: (b) => req("POST", "/api/programs", b),
  persons: (accountId) => req("GET", `/api/persons?account_id=${accountId}&include_valence=true`),
  createPerson: (b) => req("POST", "/api/persons", b),
  createStakeholder: (b) => req("POST", "/api/stakeholder-roles", b),
  createInteraction: (b) => req("POST", "/api/interactions", b),
  interaction: (id) => req("GET", `/api/interactions/${id}`),
  inbox: (status = "untriaged") => req("GET", `/api/inbox?status=${status}`),
  dismissInbox: (id) => req("POST", `/api/inbox/${id}/dismiss`),
  convertInbox: (id, body) => req("POST", `/api/inbox/${id}/convert`, body),

  // v0.2 execution
  accountExecution: (id) => req("GET", `/api/accounts/${id}/execution`),
  programExecution: (id) => req("GET", `/api/programs/${id}/execution`),
  createCommitment: (b) => req("POST", "/api/commitments", b),
  createTask: (b) => req("POST", "/api/tasks", b),
  createRisk: (b) => req("POST", "/api/risks", b),
  createIssue: (b) => req("POST", "/api/issues", b),
  createDecision: (b) => req("POST", "/api/decisions", b),
  createMilestone: (b) => req("POST", "/api/milestones", b),
  // v2 data & evidence
  scoreboard: () => req("GET", "/api/scoreboard"),
  metricDefinitions: () => req("GET", "/api/metric-definitions"),
  createMetricDefinition: (b) => req("POST", "/api/metric-definitions", b),
  benchmarks: () => req("GET", "/api/benchmarks"),
  createBenchmark: (b) => req("POST", "/api/benchmarks", b),
  valueStories: (accountId) => req("GET", `/api/value-stories${accountId ? "?account_id=" + accountId : ""}`),
  createValueStory: (b) => req("POST", "/api/value-stories", b),
  importPreview: (b) => req("POST", "/api/imports/metric-observations/preview", b),
  importCommit: (b) => req("POST", "/api/imports/metric-observations/commit", b),
  importRollback: (id) => req("POST", `/api/imports/${id}/rollback`),
  operations: () => req("GET", "/api/operations"),
  qbr: (accountId) => req("GET", `/api/accounts/${accountId}/qbr`),

  // v3 visualization
  stakeholderGraph: (accountId, programId) => req("GET", `/api/accounts/${accountId}/stakeholder-graph${programId ? "?program_id=" + programId : ""}`),
  setGraphAssessment: (roleId, b) => req("PATCH", `/api/stakeholder-roles/${roleId}/graph`, b),
  createEdge: (b) => req("POST", "/api/relationship-edges", b),
  waterfall: (accountId) => req("GET", `/api/accounts/${accountId}/waterfall`),
  stakeholderCoverage: (accountId) => req("GET", `/api/accounts/${accountId}/stakeholder-coverage`),
  observationHistory: (defId) => req("GET", `/api/metric-definitions/${defId}/observations`),

  // v4 AI & automation
  extractionConfig: () => req("GET", "/api/extraction/config"),
  runExtraction: (b) => req("POST", "/api/extraction/run", b),
  manualExtraction: (b) => req("POST", "/api/extraction/manual", b),
  acceptProposal: (id, b) => req("POST", `/api/extraction/proposals/${id}/accept`, b),
  rejectProposal: (id) => req("POST", `/api/extraction/proposals/${id}/reject`),
  plays: () => req("GET", "/api/plays"),
  createPlay: (b) => req("POST", "/api/plays", b),
  evaluatePlays: () => req("POST", "/api/plays/evaluate"),
  playRuns: (status) => req("GET", `/api/play-runs${status ? "?status=" + status : ""}`),
  completePlayRun: (id, b) => req("POST", `/api/play-runs/${id}/complete`, b),
  notifications: (unread) => req("GET", `/api/notifications${unread ? "?unread_only=true" : ""}`),
  readNotification: (id) => req("POST", `/api/notifications/${id}/read`),
  brief: (programId) => req("GET", `/api/programs/${programId}/brief`),

  // v1 commercial & deployment
  expansions: (accountId) => req("GET", `/api/accounts/${accountId}/expansions`),
  createExpansion: (b) => req("POST", "/api/expansions", b),
  patchExpansion: (id, b) => req("PATCH", `/api/expansions/${id}`, b),
  closeExpansion: (id, b) => req("POST", `/api/expansions/${id}/close`, b),
  contracts: (accountId) => req("GET", `/api/accounts/${accountId}/contracts`),
  createContract: (b) => req("POST", "/api/contracts", b),
  setOverlay: (id, b) => req("POST", `/api/contracts/${id}/overlay`, b),
  programDelivery: (programId) => req("GET", `/api/programs/${programId}/delivery`),
  createGate: (b) => req("POST", "/api/phase-gates", b),
  toggleGateItem: (id, b) => req("POST", `/api/gate-items/${id}/toggle`, b),
  waiveGate: (id, b) => req("POST", `/api/phase-gates/${id}/waive`, b),
  createMoment: (b) => req("POST", "/api/deployment-moments", b),
  createCompliance: (b) => req("POST", "/api/compliance-items", b),
  patchCompliance: (id, b) => req("PATCH", `/api/compliance-items/${id}`, b),
  createScopeChange: (b) => req("POST", "/api/scope-changes", b),
  patchGovernance: (programId, b) => req("PATCH", `/api/programs/${programId}/governance`, b),

  history: (accountId, { personId, programId } = {}) => {
    const p = new URLSearchParams();
    if (personId) p.set("person_id", personId);
    if (programId) p.set("program_id", programId);
    const qs = p.toString();
    return req("GET", `/api/accounts/${accountId}/history${qs ? "?" + qs : ""}`);
  },
  teamUpdate: (since) => req("GET", `/api/team-update${since ? "?since=" + since : ""}`),
  accountMap: (accountId) => req("GET", `/api/accounts/${accountId}/map`),
  mapPromote: (b) => req("POST", "/api/map/promote", b),
  queue: () => req("GET", "/api/queue"),
  snoozeQueue: (b) => req("POST", "/api/queue/snooze", b),
  resolveQueue: (b) => req("POST", "/api/queue/resolve", b),
  setStatus: (accountId, b) => req("POST", `/api/accounts/${accountId}/status`, b),
  closeCommitment: (id, b) => req("POST", `/api/commitments/${id}/close`, b),
  closeTask: (id, b) => req("POST", `/api/tasks/${id}/close`, b),
  closeRisk: (id, b) => req("POST", `/api/risks/${id}/close`, b),
  resolveIssue: (id, b) => req("POST", `/api/issues/${id}/resolve`, b),
  completeMilestone: (id, b) => req("POST", `/api/milestones/${id}/complete`, b),

  // Phase 3 Stage 1 — onboarding, checklists, org-chart placeholders
  onboard: (accountId, b) => req("POST", `/api/accounts/${accountId}/onboard`, b),
  onboarding: (accountId) => req("GET", `/api/accounts/${accountId}/onboarding`),
  deckSkeleton: (accountId, programId) => req("GET", `/api/accounts/${accountId}/deck-skeleton${programId ? "?program_id=" + programId : ""}`),
  intakeParse: (text) => req("POST", "/api/intake/parse", { text }),
  intakeAccept: (b) => req("POST", "/api/intake/accept", b),
  checklistItems: ({ accountId, programId, section } = {}) => {
    const p = new URLSearchParams();
    if (accountId) p.set("account_id", accountId);
    if (programId) p.set("program_id", programId);
    if (section) p.set("section", section);
    return req("GET", `/api/checklist-items?${p.toString()}`);
  },
  addChecklistItem: (b) => req("POST", "/api/checklist-items", b),
  patchChecklistItem: (id, b) => req("PATCH", `/api/checklist-items/${id}`, b),
  createPlaceholder: (b) => req("POST", "/api/placeholders", b),
  convertPlaceholder: (personId, b) => req("POST", `/api/placeholders/${personId}/convert`, b),

  // Phase 3 Stage 2 — People module core (layers, taxonomy, person card)
  peopleTaxonomy: () => req("GET", "/api/people/taxonomy"),
  personCard: (personId) => req("GET", `/api/persons/${personId}/card`),
  patchPerson: (personId, b) => req("PATCH", `/api/persons/${personId}`, b),
  patchStakeholderRole: (roleId, b) => req("PATCH", `/api/stakeholder-roles/${roleId}`, b),
  createAdvocacyEvent: (b) => req("POST", "/api/advocacy-events", b),

  // Phase 3 Stage 4 — communications ingestion + association
  ingestFixtures: () => req("GET", "/api/ingest/fixtures"),
  syncInbox: () => req("POST", "/api/ingest/emails/sync"),
  ingestRecording: (b) => req("POST", "/api/ingest/recording", b),
  accountComms: (accountId) => req("GET", `/api/accounts/${accountId}/comms`),
  flaggedComms: () => req("GET", "/api/comms/flagged"),
  unresolvedComms: () => req("GET", "/api/comms/unresolved"),
  associateComm: (id, b) => req("POST", `/api/comms/${id}/associate`, b),
  commResponded: (id) => req("POST", `/api/comms/${id}/responded`),
};
