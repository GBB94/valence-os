# Valence OS — connection registry

This is the single data-governance gate for external systems. The application is built and
tested end to end with synthetic data, but it connects to nothing real by default. Credentials
alone never authorize a connection.

Runtime state is defined in `backend/app/connections.py` and shown on the Operations screen.
The Stage 8 tests require every runtime boundary below to remain represented here.

## Approval contract

A connection may move to a real mode only after all of these are true:

1. Valence has completed the hosting and data-handling review.
2. The boundary-specific requirements below are satisfied and tested with synthetic data first.
3. The change is recorded as a new entry in `decisions.md`, including provider, scopes, region,
   retention, credentials owner, rollback, and approval owner.
4. The deployment sets both `VALENCE_OS_REAL_CONNECTIONS_APPROVED=1` and
   `VALENCE_OS_REAL_CONNECTIONS_DECISION=<decision reference>` through managed secrets/config.
5. Operations reports the intended mode and `approved`; a rollback returns the boundary to its
   local/mock mode and removes the approval configuration.

Never store credentials, tokens, real client payloads, or approval evidence in this repository.
The environment variables are a fail-closed runtime check, not a substitute for the review.

## Registry

| ID | Boundary | Current mode | Mock fixture set | Runtime switch | A real connection requires |
|---|---|---|---|---|---|
| `recording_source` | Recording and transcript intake | Local fixture name or pasted transcript | `backend/app/fixtures/transcripts/*.txt` | None | Approved recording store/upload location; retention and deletion policy; service identity |
| `transcription_source` | Audio transcription | Mock transcript lookup | `backend/app/fixtures/transcripts/*.txt` | None; no real adapter implemented | Approved provider and DPA; processing region; retention controls; credential storage; audio deletion contract |
| `email_provider` | Email provider | Parsed synthetic `.eml` files | `backend/app/fixtures/emails/*.eml` | None; no real adapter implemented | Approved Graph/Gmail scope; least privilege; retention; sync/webhook design; secret storage |
| `calendar_provider` | Calendar provider | Synthetic `.ics` reads and local write records | `backend/app/fixtures/calendar/*.ics` | None; no real adapter implemented | Approved read/write scopes; service identity; attendee-data rules; idempotency and rollback |
| `enrichment_source` | Org-change enrichment | Synthetic JSON proposals | `backend/app/fixtures/org_changes/*.json` | None; no real adapter implemented | Approved provider/fields and lawful-use review; refresh cadence; provenance; correction/deletion path |
| `headcount_source` | Population headcount source | Synthetic HRIS-shaped aggregate CSV | `backend/app/fixtures/headcount/*.csv` | None; no real adapter implemented | Approved aggregate-only export; cohort floor; dated provenance; secure transfer; no person-level product usage |
| `metric_source` | Data-team metric ingestion | Operator CSV preview → commit → rollback | None | None; no real adapter implemented | Approved aggregate cohort feed; stable metric/population IDs; freshness contract; rollback and cohort-floor enforcement |
| `notification_channel` | Notification delivery | In-app SQLite notifications only | None | None; no outbound adapter implemented | Approved channel/recipients; least-sensitive payload; delivery audit; retry and disable controls |
| `llm_endpoint` | LLM extraction and intake endpoint | Offline mock by default; manual local paste is also local | Transcript fixtures | `EXTRACTOR_BACKEND=mock\|api`; API is fail-closed behind the approval contract | Approved provider/model; DPA/region; credential storage; retention review; model allow-list; logged decision |
| `copilot_endpoint` | Account Copilot cross-record context endpoint | Deterministic offline mock; no real adapter | `backend/app/fixtures/copilot/*.json` | `COPILOT_BACKEND=mock`; any real mode fails closed behind a distinct approval | Separate cross-record payload review; bounded field allow-list and context; provider/model and region; retention/training terms; redacted logs; rollback configuration; logged decision |
| `company_intel_source` | Public company artifact source | Synthetic JSON snapshots only | `backend/app/fixtures/company_intel/*.json` | `COMPANY_INTEL_BACKEND=mock` only; any real mode fails closed because no retrieval adapter exists | Provider terms/content license; API/robots compliance; source allow-list; exact provenance; retention; correction/takedown; credentials/logging; rollback |
| `intel_extraction_endpoint` | Public artifact → company-event extraction | Fixture-carried proposals; no extraction call | `backend/app/fixtures/company_intel/*.json` | None; no extraction implementation | Separate model/provider and payload approval; licensing; region/retention; prompt-injection controls; golden evaluation; credentials/logging; rollback |
| `file_storage` | Files and generated artifacts | Source links + SQLite markdown; binary export rendered in memory | None | None; no object-store adapter implemented | Approved encrypted object store; account boundaries; signed links; retention/deletion; backup and restore test |
| `hosting` | Application hosting and database | Local FastAPI + SQLite + optional in-process worker | Synthetic seed database | `VALENCE_OS_DB`; `VALENCE_OS_WORKER` | Approved hosting; SSO/MFA; encryption; managed secrets; network/logging controls; backups, restore drill, incident owner |

## Boundary notes

- The optional Anthropic implementation is code-complete but is a **real** outbound connection.
  `EXTRACTOR_BACKEND=api` is rejected unless the approval contract is present, even when an API
  credential happens to exist on the machine.
- Extraction approval does not authorize Copilot payloads. `COPILOT_BACKEND` has its own registry
  entry and approval class; Stage 12 implements only the deterministic mock and deliberately has no
  network adapter.
- Company retrieval and company-event extraction are two independent approvals. Stage 14 performs
  neither: exact public excerpts and proposed structured events arrive together in synthetic
  fixtures. Public availability does not waive content licensing or correction/takedown duties.
- Manual local-LLM mode makes no call from Valence OS: the operator runs their own local model and
  pastes schema-validated JSON. Proposals still require per-item acceptance.
- Email, transcripts, calendar, enrichment, headcount, metrics, and generated client artifacts may
  contain customer data in production. They remain separate boundaries even if one future vendor
  supplies several of them.
- Named-person Nadia usage is prohibited at every boundary. Usage and outcomes enter only as
  aggregate cohorts/cells, subject to the account's cohort floor and freshness rules.
- “Sent” on a generated document records an operator assertion. Valence OS has no outbound document
  delivery adapter.

## Pre-production verification

- [ ] Approval decision exists and names an accountable owner.
- [ ] Data classification and field allow-list reviewed for this boundary.
- [ ] Least-privilege scopes and managed secrets verified.
- [ ] Synthetic contract, retry, idempotency, and rollback tests pass.
- [ ] Retention, deletion, audit, backup, and incident procedures have owners.
- [ ] Operations shows the expected mode; no unrelated boundary changed.
- [ ] Trust-boundary suite passes: aggregate-only usage, promoted-only client output, dated
      stakeholder evidence, and stale metrics rendering unknown.
