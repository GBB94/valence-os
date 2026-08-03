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
    const error = new Error(detail);
    error.status = res.status;
    throw error;
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
  sourceReferences: () => req("GET", "/api/source-references"),
  patchSourceReference: (id, b) => req("PATCH", `/api/source-references/${id}`, b),
  accounts: () => req("GET", "/api/accounts"),
  account: (id) => req("GET", `/api/accounts/${id}`),
  companyWorkspace: (id) => req("GET", `/api/accounts/${id}/company`),
  putCompanyWatch: (id, b) => req("PUT", `/api/accounts/${id}/company-watch`, b),
  syncCompanyIntel: () => req("POST", "/api/ingest/company-intel/sync"),
  confirmCompanyEvent: (id, b = {}) => req("POST", `/api/intel/events/${id}/confirm`, b),
  dismissCompanyEvent: (id, b) => req("POST", `/api/intel/events/${id}/dismiss`, b),
  confirmCompanyEventLink: (eventId, linkId, b = {}) => req("POST", `/api/intel/events/${eventId}/links/${linkId}/confirm`, b),
  dismissCompanyEventLink: (eventId, linkId, b) => req("POST", `/api/intel/events/${eventId}/links/${linkId}/dismiss`, b),
  createCompanyEventLink: (eventId, b) => req("POST", `/api/intel/events/${eventId}/links`, b),
  suggestCompanyEventLinks: (eventId) => req("POST", `/api/intel/events/${eventId}/links/suggest`),
  createCompanyLinkKeyword: (accountId, b) => req("POST", `/api/accounts/${accountId}/intel/link-keywords`, b),
  retractIntelDocument: (id, b) => req("POST", `/api/intel/documents/${id}/retract`, b),
  evaluateCompanyIntel: (id) => req("POST", `/api/accounts/${id}/intel/evaluate`),
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
  accountMetricObservations: (accountId) => req("GET", `/api/accounts/${accountId}/metric-observations`),

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

  // Phase 3 Stage 5 — relationship intelligence
  championPipeline: (accountId) => req("GET", `/api/accounts/${accountId}/champion-pipeline`),
  createChampion: (b) => req("POST", "/api/champion-candidates", b),
  patchChampion: (id, b) => req("PATCH", `/api/champion-candidates/${id}`, b),
  influencePaths: (accountId, target) => req("GET", `/api/accounts/${accountId}/influence-paths?target=${target}`),
  execAlignment: (accountId) => req("GET", `/api/accounts/${accountId}/exec-alignment`),
  createExecPairing: (b) => req("POST", "/api/exec-pairings", b),
  patchExecPairing: (id, b) => req("PATCH", `/api/exec-pairings/${id}`, b),
  messagingLibrary: ({ layer = "", role = "" } = {}) => {
    const p = new URLSearchParams();
    if (layer) p.set("layer", layer); if (role) p.set("role", role);
    const qs = p.toString();
    return req("GET", `/api/messaging-library${qs ? "?" + qs : ""}`);
  },
  createMessaging: (b) => req("POST", "/api/messaging-library", b),
  patchMessaging: (id, b) => req("PATCH", `/api/messaging-library/${id}`, b),
  meetingDynamics: (programId) => req("GET", `/api/programs/${programId}/meeting-dynamics`),
  pullSignals: (accountId) => req("GET", `/api/accounts/${accountId}/pull-signals`),
  createPullSignal: (b) => req("POST", "/api/pull-signals", b),

  // Stage 5.5 — whitespace map, value ledger, funding intelligence
  whitespace: (accountId) => req("GET", `/api/accounts/${accountId}/whitespace`),
  nextSeats: (accountId) => req("GET", `/api/accounts/${accountId}/whitespace/next-seats`),
  cell: (id) => req("GET", `/api/whitespace-cells/${id}`),
  createCell: (b) => req("POST", "/api/whitespace-cells", b),
  patchCell: (id, b) => req("PATCH", `/api/whitespace-cells/${id}`, b),
  setCellFact: (id, b) => req("POST", `/api/whitespace-cells/${id}/set-fact`, b),
  reopenCell: (id, b) => req("POST", `/api/whitespace-cells/${id}/reopen`, b),
  linkCellEvidence: (id, b) => req("POST", `/api/whitespace-cells/${id}/evidence`, b),
  partition: (accountId) => req("GET", `/api/accounts/${accountId}/population-partition`),
  createPartition: (b) => req("POST", "/api/population-partitions", b),
  createSegment: (b) => req("POST", "/api/population-segments", b),
  patchSegment: (id, b) => req("PATCH", `/api/population-segments/${id}`, b),
  headcountHistory: (id) => req("GET", `/api/population-segments/${id}/headcount-history`),
  createHeadcountObs: (b) => req("POST", "/api/population-headcount-observations", b),
  populationViews: (accountId) => req("GET", `/api/accounts/${accountId}/population-views`),
  createPopulationView: (b) => req("POST", "/api/population-views", b),
  audienceTags: () => req("GET", "/api/audience-tags"),
  createAudienceTag: (b) => req("POST", "/api/audience-tags", b),
  useCases: (accountId) => req("GET", `/api/use-cases${accountId ? `?account_id=${accountId}` : ""}`),
  createUseCase: (b) => req("POST", "/api/use-cases", b),
  ledger: (accountId) => req("GET", `/api/accounts/${accountId}/ledger`),
  valueGaps: (accountId) => req("GET", `/api/accounts/${accountId}/value-gaps`),
  createValueTarget: (b) => req("POST", "/api/value-targets", b),
  supersedeValueTarget: (id, b) => req("POST", `/api/value-targets/${id}/supersede`, b),
  linkValueTargetEvidence: (id, b) => req("POST", `/api/value-targets/${id}/evidence`, b),
  funding: (accountId) => req("GET", `/api/accounts/${accountId}/funding`),
  createFundingPool: (b) => req("POST", "/api/funding-pools", b),
  patchFundingPool: (id, b) => req("PATCH", `/api/funding-pools/${id}`, b),
  putFiscalMap: (accountId, b) => req("PUT", `/api/accounts/${accountId}/fiscal-map`, b),
  createAskCalendar: (b) => req("POST", "/api/ask-calendars", b),
  patchAskStep: (id, b) => req("PATCH", `/api/ask-calendar-steps/${id}`, b),
  revenueMovement: (accountId) => req("GET", `/api/accounts/${accountId}/revenue-movement`),
  patchContractRevenue: (id, b) => req("PATCH", `/api/contracts/${id}/revenue`, b),
  accountSettings: (accountId) => req("GET", `/api/accounts/${accountId}/settings`),
  putAccountSettings: (accountId, b) => req("PUT", `/api/accounts/${accountId}/settings`, b),

  // Stage 7 — recurring signal episodes, mock calendar, and org change
  stage7Fixtures: () => req("GET", "/api/stage7/fixtures"),
  syncCalendar: () => req("POST", "/api/ingest/calendar/sync"),
  syncOrgChanges: () => req("POST", "/api/ingest/org-changes/sync"),
  syncHeadcount: () => req("POST", "/api/ingest/headcount/sync"),
  calendarEvents: (accountId) => req("GET", `/api/accounts/${accountId}/calendar-events`),
  createCalendarEvent: (b) => req("POST", "/api/calendar-events", b),
  orgChanges: (accountId) => req("GET", `/api/accounts/${accountId}/org-changes`),
  confirmOrgChange: (id) => req("POST", `/api/org-change-flags/${id}/confirm`, {}),
  dismissOrgChange: (id, reason) => req("POST", `/api/org-change-flags/${id}/dismiss`, { reason }),
  completeSuccession: (id, b) => req("POST", `/api/succession-records/${id}/complete`, b),
  evaluateSignals: () => req("POST", "/api/signals/evaluate"),
  signalEpisodes: ({ accountId = "", status = "" } = {}) => {
    const p = new URLSearchParams();
    if (accountId) p.set("account_id", accountId); if (status) p.set("status", status);
    const qs = p.toString();
    return req("GET", `/api/signal-episodes${qs ? "?" + qs : ""}`);
  },
  dismissSignal: (id, reason) => req("POST", `/api/signal-episodes/${id}/dismiss`, { reason }),
  draftSignalOpportunity: (id) => req("POST", `/api/signal-episodes/${id}/draft-opportunity`),

  // Stage 7.5 — qualification, operational agreements, renewal, and growth plan
  opportunityQualification: (id) => req("GET", `/api/expansions/${id}/qualification`),
  patchOpportunityQualification: (id, b) => req("PATCH", `/api/expansions/${id}/qualification`, b),
  operationalAgreements: (accountId) => req("GET", `/api/accounts/${accountId}/operational-agreements`),
  createOperationalAgreement: (b) => req("POST", "/api/operational-agreements", b),
  evaluateOperationalAgreements: () => req("POST", "/api/operational-agreements/evaluate"),
  actionOperationalAgreement: (id) => req("POST", `/api/operational-agreement-events/${id}/action`),
  dismissOperationalAgreement: (id, reason) => req("POST", `/api/operational-agreement-events/${id}/dismiss`, { dismissal_reason: reason }),
  renewalCenter: (accountId, contractId = "") => req("GET", `/api/accounts/${accountId}/renewal-center${contractId ? `?contract_id=${contractId}` : ""}`),
  growthPlan: (accountId) => req("GET", `/api/accounts/${accountId}/growth-plan`),
  createGrowthPlan: (b) => req("POST", "/api/growth-plans", b),
  createGrowthPlanLine: (b) => req("POST", "/api/growth-plan-lines", b),
  patchGrowthPlanLine: (id, b) => req("PATCH", `/api/growth-plan-lines/${id}`, b),

  // Stage 9 — portfolio analytics and expansion learning
  commercialAnalytics: (windowDays = 90) => req("GET", `/api/portfolio/commercial-analytics?window_days=${windowDays}`),
  playbookEntries: (accountId = "") => req("GET", `/api/playbook-entries${accountId ? `?account_id=${accountId}` : ""}`),
  createPlaybookEntry: (b) => req("POST", "/api/playbook-entries", b),
  playbookMatches: (cellId) => req("GET", `/api/whitespace-cells/${cellId}/playbook-matches`),
  promotePlaybookPlay: (id, b) => req("POST", `/api/playbook-entries/${id}/promote-play`, b),
  promotePlaybookMessage: (id, b) => req("POST", `/api/playbook-entries/${id}/promote-message`, b),

  // Stage 6 — generators as finished artifacts
  generatePreview: (kind, accountId, programId = "") => {
    const path = { pre_call_brief: "pre-call-brief", business_case: "business-case",
                   value_review: "value-review", champion_kit: "champion-kit",
                   kickoff_deck: "kickoff-deck" }[kind];
    const qs = programId && ["pre_call_brief", "kickoff_deck"].includes(kind)
      ? `?program_id=${encodeURIComponent(programId)}` : "";
    return req("GET", `/api/accounts/${accountId}/${path}${qs}`);
  },
  documents: ({ accountId = "", status = "" } = {}) => {
    const p = new URLSearchParams();
    if (accountId) p.set("account_id", accountId);
    if (status) p.set("status", status);
    const qs = p.toString();
    return req("GET", `/api/documents${qs ? "?" + qs : ""}`);
  },
  saveDocument: (accountId, b) => req("POST", `/api/accounts/${accountId}/documents`, b),
  patchDocument: (id, b) => req("PATCH", `/api/documents/${id}`, b),
  setDocumentStatus: (id, b) => req("POST", `/api/documents/${id}/status`, b),
  // Download links are plain hrefs, so they need the absolute base the fetch client uses.
  documentPptxUrl: (id) => `${BASE}/api/documents/${id}/pptx`,
  documentPdfUrl: (id) => `${BASE}/api/documents/${id}/pdf`,
  kickoffPptxUrl: (accountId) => `${BASE}/api/accounts/${accountId}/kickoff-deck/pptx`,
  roiModel: (accountId) => req("GET", `/api/accounts/${accountId}/roi-model`),
  putRoiModel: (accountId, b) => req("PUT", `/api/accounts/${accountId}/roi-model`, b),
  recoveredSpend: (accountId) => req("GET", `/api/accounts/${accountId}/recovered-spend`),
  scheduleWeeklyUpdate: (b) => req("POST", "/api/weekly-team-update/schedule", b),
  jobs: (status = "") => req("GET", `/api/jobs${status ? `?status=${status}` : ""}`),
  runJobs: () => req("POST", "/api/jobs/run", {}),

  // Internal operating layer
  forecastPeriods: () => req("GET", "/api/forecast-periods"),
  createForecastPeriod: (b) => req("POST", "/api/forecast-periods", b),
  forecastEntries: (id) => req("GET", `/api/forecast-periods/${id}/entries`),
  createForecastEntry: (id, b) => req("POST", `/api/forecast-periods/${id}/entries`, b),
  changeForecastCategory: (id, b) => req("POST", `/api/forecast-entries/${id}/category`, b),
  lockForecastPeriod: (id) => req("POST", `/api/forecast-periods/${id}/lock`),
  submitForecast: (id) => req("POST", `/api/forecast-periods/${id}/submissions`),
  closeForecastPeriod: (id) => req("POST", `/api/forecast-periods/${id}/close`),
  forecastCalibration: (id) => req("GET", `/api/forecast-periods/${id}/calibration`),
  internalFunctions: () => req("GET", "/api/internal-functions"),
  internalAsks: (id) => req("GET", `/api/accounts/${id}/internal-asks`),
  createInternalAsk: (id, b) => req("POST", `/api/accounts/${id}/internal-asks`, b),
  setInternalAskStatus: (id, b) => req("POST", `/api/internal-asks/${id}/status`, b),
  escalateAsk: (id, b) => req("POST", `/api/internal-asks/${id}/escalations`, b),
  reviews: (id) => req("GET", `/api/accounts/${id}/reviews`),
  createReview: (id, b) => req("POST", `/api/accounts/${id}/reviews`, b),
  holdReview: (id, b) => req("POST", `/api/account-reviews/${id}/hold`, b),
  operatorViews: (id) => req("GET", `/api/accounts/${id}/operator-views`),
  createOperatorView: (id, b) => req("POST", `/api/accounts/${id}/operator-views`, b),
  assessInternalStatus: (id, b) => req("POST", `/api/accounts/${id}/status-assessments`, b),
  generateReviewDocument: (id, kind) => req("POST", `/api/account-reviews/${id}/documents/${kind}`, {}),
  internalRoster: (id) => req("GET", `/api/accounts/${id}/internal-roster`),
  addInternalRoster: (id, b) => req("POST", `/api/accounts/${id}/internal-roster`, b),
  coverage: (id) => req("GET", `/api/accounts/${id}/coverage`),
  coverageBrief: (id) => req("GET", `/api/accounts/${id}/coverage-brief`),
  colleagueCallBrief: (id, rosterId) => req("GET", `/api/accounts/${id}/call-brief?roster_id=${rosterId}`),
  coverageReturnBrief: (id, startsOn, endsOn) => req("GET", `/api/accounts/${id}/return-brief?starts_on=${startsOn}&ends_on=${endsOn}`),
  productFeedback: (accountId = "") => req("GET", `/api/product-feedback${accountId ? `?account_id=${accountId}` : ""}`),
  createProductFeedback: (b) => req("POST", "/api/product-feedback", b),
  addFeedbackOccurrence: (id, b) => req("POST", `/api/product-feedback/${id}/occurrences`, b),
  setFeedbackStatus: (id, b) => req("POST", `/api/product-feedback/${id}/status`, b),
  recordFeedbackTouch: (id, b) => req("POST", `/api/product-feedback-occurrences/${id}/touches`, b),
  internalAnalytics: () => req("GET", "/api/portfolio/internal-analytics"),
  monthlyInternalPreview: () => req("GET", "/api/internal-reports/monthly_portfolio_brief/preview"),
  generateMonthlyInternal: () => req("POST", "/api/internal-reports/monthly_portfolio_brief/documents", {}),
  excludeInternalReportOrigin: (b) => req("POST", "/api/internal-reports/red-origin-exclusions", b),

  // Stage 11 — adoption campaigns
  campaigns: (accountId, status) => req("GET",
    `/api/accounts/${accountId}/campaigns${status ? `?status=${status}` : ""}`),
  campaign: (id) => req("GET", `/api/campaigns/${id}`),
  createCampaign: (b) => req("POST", "/api/campaigns", b),
  patchCampaign: (id, b) => req("PATCH", `/api/campaigns/${id}`, b),
  campaignReadiness: (id) => req("GET", `/api/campaigns/${id}/readiness`),
  // Stage 11.2 — learning
  campaignRetrospective: (id) => req("GET", `/api/campaigns/${id}/retrospective`),
  recordCampaignRetrospective: (id, b) => req("POST", `/api/campaigns/${id}/retrospective`, b),
  campaignNearest: (id) => req("GET", `/api/campaigns/${id}/nearest`),
  campaignLearning: () => req("GET", "/api/portfolio/campaign-learning"),
  campaignTransition: (id, action, b) => req("POST", `/api/campaigns/${id}/${action}`, b),
  addCampaignBarrier: (id, b) => req("POST", `/api/campaigns/${id}/barriers`, b),
  addCampaignTarget: (id, b) => req("POST", `/api/campaigns/${id}/targets`, b),
  addCampaignPlanLink: (id, b) => req("POST", `/api/campaigns/${id}/plan`, b),
  addCampaignCheckpoint: (id, b) => req("POST", `/api/campaigns/${id}/checkpoints`, b),

  // Stage 13 — planned communication waves and privacy-safe session attendance
  commsSequences: (accountId) => req("GET", `/api/accounts/${accountId}/comms-sequences`),
  commsSequence: (id) => req("GET", `/api/comms-sequences/${id}`),
  createCommsSequence: (b) => req("POST", "/api/comms-sequences", b),
  cancelCommsSequence: (id, reason) => req("POST", `/api/comms-sequences/${id}/cancel`, { reason }),
  createCommsWave: (id, b) => req("POST", `/api/comms-sequences/${id}/waves`, b),
  patchCommsWave: (id, b) => req("PATCH", `/api/comms-waves/${id}`, b),
  markCommsWaveSent: (id, sentAt = null) => req("POST", `/api/comms-waves/${id}/sent`, { sent_at: sentAt }),
  cancelCommsWave: (id) => req("POST", `/api/comms-waves/${id}/cancel`, {}),
  createCommsSession: (b) => req("POST", "/api/comms-sessions", b),
  recordSessionAttendee: (id, b) => req("PUT", `/api/calendar-events/${id}/attendees`, b),
  sessionAttendance: (id) => req("GET", `/api/calendar-events/${id}/attendance`),

  proposeCampaignFromSignal: (episodeId, b) =>
    req("POST", `/api/signal-episodes/${episodeId}/propose-campaign`, b),
  attachEpisodeToCampaign: (episodeId, campaignId) =>
    req("POST", `/api/signal-episodes/${episodeId}/attach-campaign`, { campaign_id: campaignId }),
  supersedeCampaignPlanLink: (linkId, b) =>
    req("POST", `/api/campaign-plan-links/${linkId}/supersede`, b),

  // Stage 12 — grounded, read-only Account Copilot
  createCopilotRun: (b) => req("POST", "/api/copilot/runs", b),
  copilotRun: (id) => req("GET", `/api/copilot/runs/${id}`),
  copilotRuns: ({ scopeType = "", accountId = "", programId = "" } = {}) => {
    const p = new URLSearchParams();
    if (scopeType) p.set("scope_type", scopeType); if (accountId) p.set("account_id", accountId);
    if (programId) p.set("program_id", programId);
    return req("GET", `/api/copilot/runs?${p.toString()}`);
  },
  copilotFeedback: (id, b) => req("POST", `/api/copilot/runs/${id}/feedback`, b),
  copilotMarkReviewed: (id) => req("POST", `/api/copilot/runs/${id}/mark-reviewed`, {}),
  copilotDraftPreview: (id, b) => req("POST", `/api/copilot/runs/${id}/draft-preview`, b),
  copilotDraft: (id, b) => req("POST", `/api/copilot/runs/${id}/draft`, b),
  copilotHealth: () => req("GET", "/api/copilot/health"),
  copilotConfigurations: () => req("GET", "/api/copilot/configurations"),
  activateCopilotConfiguration: (id) => req("POST", `/api/copilot/configurations/${id}/activate`, {}),
  rollbackCopilotConfiguration: (id) => req("POST", `/api/copilot/configurations/${id}/rollback`, {}),
  copilotFeedbackQueue: (pendingOnly = true) => req("GET", `/api/copilot/feedback?pending_only=${pendingOnly}`),
  reviewCopilotFeedback: (id, b) => req("POST", `/api/copilot/feedback/${id}/review`, b),
  copilotAliases: (accountId = "") => req("GET", `/api/copilot/entity-aliases${accountId ? `?account_id=${accountId}` : ""}`),
  createCopilotAlias: (b) => req("POST", "/api/copilot/entity-aliases", b),
  copilotStyles: () => req("GET", "/api/copilot/styles"),
  createCopilotStyle: (b) => req("POST", "/api/copilot/styles", b),
};
