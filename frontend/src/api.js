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
  accounts: () => req("GET", "/api/accounts"),
  account: (id) => req("GET", `/api/accounts/${id}`),
  createAccount: (b) => req("POST", "/api/accounts", b),
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
  queue: () => req("GET", "/api/queue"),
  snoozeQueue: (b) => req("POST", "/api/queue/snooze", b),
  resolveQueue: (b) => req("POST", "/api/queue/resolve", b),
  setStatus: (accountId, b) => req("POST", `/api/accounts/${accountId}/status`, b),
  closeCommitment: (id, b) => req("POST", `/api/commitments/${id}/close`, b),
  closeTask: (id, b) => req("POST", `/api/tasks/${id}/close`, b),
  closeRisk: (id, b) => req("POST", `/api/risks/${id}/close`, b),
  resolveIssue: (id, b) => req("POST", `/api/issues/${id}/resolve`, b),
  completeMilestone: (id, b) => req("POST", `/api/milestones/${id}/complete`, b),
};
