# Valence OS — Company Intelligence Spec

### Outside-in monitoring of what an account company says and does publicly, mapped to whitespace and attention

*v2 · August 2026 · **accepted as Stage 14 authority by Zach on 2026-08-02 (D-110)** · additive after Stage 13*

Authority it extends: `EXPANSION-ENGINE-SPEC.md` (whitespace and Stage 7 signals), `ACCOUNT-COPILOT-SPEC.md` (grounding and citations), and `PHASE-3-SPEC.md`. `CLAUDE.md` trust boundaries, mock-only data, internal-only outputs, no auto-send, and D-83 no-re-gating remain binding.

This revision incorporates an adversarial product and engineering review against primary documentation from AlphaSense, Common Room, 6sense, Clay, LinkedIn Sales Navigator, SEC EDGAR, and the Congressional Research Service. The review changed four load-bearing choices from v1: company identity is independent of an account, citations point to exact spans rather than whole documents, convergence persists and proves independent source lineage, and source corrections/retractions propagate into derived events and episodes.

---

## 0. Product contract and boundary

The operator opens an account and sees, with exact citations to dated public sources, what the company has publicly said and done and where it may land on the whitespace map. The system never claims more than its stored snapshots entail.

Stage 14 is:

- an adapter-fed, proposal-first record of public company artifacts;
- structured, dated, decaying company events grounded in exact evidence spans;
- operator-confirmed links to account, whitespace rows/columns/cells, and stakeholders;
- a signal episode only when independently sourced events converge; and
- a fixed-section, grounded company brief over confirmed evidence.

It is not a scraper, a numeric intent/opportunity score, a writer of whitespace facts, a cause-finder, a person-surveillance product, or a client-facing output. Real retrieval and model extraction remain separately governed connection boundaries and fail closed.

## 1. Design rules

1. **Entity is not account.** A canonical company can be linked to several account records, subsidiaries, or historical relationships. Provider identifiers are scoped by scheme/provider and effective dates.
2. **Feed and brief are both cited.** The feed exposes exact source spans; the brief uses fixed sections with citations on every factual bullet.
3. **Proposal-first.** Imported events and suggested map links start `proposed`. Only confirmed, non-expired events affect overlays, convergence, briefs, or attention.
4. **Independent convergence, not volume.** Two republications of one announcement are one occurrence, not corroboration. A convergence episode must name different event kinds, distinct canonical occurrences, and independent origin groups.
5. **Temporal semantics are explicit.** `occurred_on`, `published_on`, `observed_at`, precision, effective interval, and expiry are different facts. Unknown dates stay unknown.
6. **Each kind decays differently.** Stale events expire; nothing silently carries forward.
7. **Hiring uses posting-level facts.** A raw posting may be duplicated, reposted, closed, or stale. Clusters are derived from active, deduplicated postings and remain proposed until reviewed. CRS notes there is no official prevalence estimate for “ghost jobs”; Stage 14 therefore makes no unsupported prevalence claim.
8. **Contraction is not inverted.** Restructuring and layoffs remain contraction evidence and hold vendor-push candidates.
9. **Corrections propagate.** Superseding, retracting, or losing the last live evidence invalidates dependent events and reevaluates their overlays and episodes.
10. **Review debt is not evidence.** Proposed-event counts may nudge review in Today, but they never appear inside a generated brief or evidence packet.

## 2. Canonical company identity and watch policy

`company_entities` holds stable company identity separately from CRM/account identity. `company_identifiers` stores domains, CIKs, LEIs, tickers, and provider IDs with provider/jurisdiction and effective dates. `account_company_links` maps an account to a company as `primary`, `parent`, `subsidiary`, `division`, or `acquisition_target`; one active primary link is allowed per account.

This is load-bearing: exact account-name matching is not an identity system. CIK is the primary public-company anchor in SEC-backed real mode; domain and provider IDs are secondary. Fixtures resolve by an explicit identifier or a single unambiguous alias. Ambiguous/unknown items are counted `unmatched` and skipped, never guessed.

`company_watch_profiles`, one per account, owns operator policy: `standard | elevated | paused`, source/topic include/exclude lists, languages, cadence, hiring thresholds, and maximum convergence gap. Identity changes do not rewrite watch policy or history.

A private company has no assumed filing/earnings coverage. Missing source classes render as coverage gaps, not negative evidence.

## 3. Immutable artifacts and span-level evidence

`intel_documents` stores immutable versions of public artifacts with company, provider-scoped external ID, kind, publisher, source URL, publication/retrieval timestamps, content hash, source role (`original | republication | commentary`), canonical source key, origin group, and correction state (`active | superseded | retracted`). Content is a bounded mock excerpt in Stage 14.

`intel_document_spans` stores exact locators and bounded excerpts (page/section/paragraph/timecode), hashes, and optional speaker/section. Events cite spans through `company_event_evidence`; a whole-document citation is not sufficient. A correction creates a new document version and supersedes the old one. Retraction or supersession preserves history but removes non-live evidence from active derivations.

All retrieved prose is untrusted. It is quarantined from planning instructions and screened by the existing copilot injection controls. Documents/events are internal-only and not promotable in this stage.

## 4. Structured company events

An event is a dated assertion grounded in at least one span. `company_event_kinds` is governed data, seeded with:

| Key | Direction | Default decay |
|---|---|---:|
| `leadership_change` | neutral | 120 days |
| `m_and_a` | expansion | 540 days |
| `funding_or_investment` | expansion | 30 days |
| `strategic_initiative` | expansion | 90 days |
| `hiring_cluster` | expansion | 28 days |
| `geo_or_facility_expansion` | expansion | 180 days |
| `restructuring_or_layoffs` | contraction | 180 days |
| `partnership_or_alliance` | neutral | 90 days |
| `regulatory_or_compliance` | neutral | 180 days |

Event status is `proposed | confirmed | dismissed | superseded | retracted | invalidated`. Confirmation requires live evidence and stamps `expires_on` from the kind default. Events additionally carry `canonical_occurrence_key`, `occurred_on`, date precision, observed time, optional effective interval, derivation version, and provider-scoped external ID. Active uniqueness is provider + external ID, never external ID alone.

Leadership payloads may hand off to the existing org-change proposal path, but cannot write stance/influence or personal sentiment. An event summary describes the role and organization in professional terms.

## 5. Hiring facts and derived clusters

`hiring_postings` stores one provider-scoped posting: external ID, company, account, function, region, title, first/last seen, state (`active | closed | unknown`), and source document/span. Reposts sharing the normalized posting key do not multiply the count.

`hiring_observations` stores derived function × region × date aggregates for history. A proposed `hiring_cluster` is derived only when the account watch policy is met (defaults: at least five active unique postings in one function × region observed within 21 days). A single posting, stale/closed postings, and postings spread across functions do not qualify. Hiring clusters cannot independently corroborate another event derived from the same origin group.

## 6. Operator mapping and outside-in overlay

`company_event_links` uses explicit nullable foreign keys rather than a polymorphic `target_type/target_id`: exactly one of account target, segment, view, use case, cell, or person is set. Triggers reject cross-account targets. Every link has a rationale and `proposed | confirmed | dismissed` lifecycle.

The account target is first-class; it is how account-wide convergence works. Matchers may suggest links from region/business-unit names, governed keywords, and resolved leadership roles. They never confirm links.

`expansion.whitespace_map` adds an optional `outside_in` overlay containing active confirmed event IDs/counts for row and column headers. The UI renders a flag glyph plus count and tooltip. It never changes cell hue, glyph, state, or facts. For the synthetic Terravance fixture, an account-wide acquisition and a strategic initiative can flag a use-case column after operator confirmation; the operator still owns any cell-fact edit.

## 7. Persisted convergence and Stage 7 bridge

Convergence is the only path from company intel into attention. A target converges when at least two active, confirmed events:

- have different event kinds;
- have distinct `canonical_occurrence_key` values;
- come from independent `origin_group` values;
- have confirmed links to the same account/row/column target; and
- have overlapping active windows with occurrence dates no farther apart than the account’s configured maximum gap.

`company_convergences` persists the evaluated target, state, rule version, first/last evaluated times, and explanation. `company_convergence_events` persists the composing event set. This makes an episode reproducible after taxonomy/configuration changes.

Stage 7 adds `source_kind='company'` and `company_convergence:{account}:{target-kind}:{target-id}`. A persisted convergence opens/refreshes one episode per account-target and stores its company-event composition. Expiry, dismissal, evidence retraction, or link removal reevaluates and closes the episode. Single events stay in the feed. Active contraction events hold vendor-push candidates with an explicit reason; they are never treated as expansion positives.

## 8. Grounded company brief

The existing copilot gains intent `company_brief` with fixed sections:

1. **Coverage and as-of** — source classes present/missing and latest retrieval.
2. **What they said** — confirmed filing, earnings, press, and regulatory events.
3. **What they did** — M&A, expansion, leadership, partnership, and contraction.
4. **Hiring picture** — confirmed clusters and factual aggregate changes.
5. **On the map** — confirmed account/row/column/cell/person links.
6. **Watch** — expiring confirmed events and active convergence composition.

Only confirmed events and live evidence spans enter the packet. Proposed-review counts are rendered separately in the Company UI/Today and never in generated prose. Each non-heading factual bullet cites a packet snapshot that includes the span locator and excerpt. Unsupported claims fail validation; missing filings for a private company produce `insufficient`, not guessed prose; expired events may only be described as expired. No causal or buying-intent forecast is permitted.

## 9. Ingestion, observability, and governance

`intel_sync_runs` and `intel_sync_items` make ingestion auditable by provider, fixture, company resolution, outcome, and error. Sync responses report run ID and created/skipped/unmatched/corrected/retracted/error counts. One bad item does not fail the batch. Dedupe is provider-scoped and idempotent.

Operations shows last successful run, freshness by source class, unmatched/error counts, proposed-review age, confirmation/dismissal/duplicate/retraction rates, and both connection-registry rows. These are operational/evaluation measures, never opportunity scores.

Two `CONNECTIONS.md` rows govern future boundaries:

1. `company_intel_source`: public-artifact fetcher; Stage 14 mode `mock_json`. Real mode requires terms/licensing, API/robots compliance, allowed providers/source classes, credentials, retention, correction/takedown, logging, and rollback.
2. `intel_extraction_endpoint`: document-to-event extraction payload; disabled in Stage 14 because fixtures contain pre-extracted proposals. It does not inherit copilot approval.

Both call `require_real_connection` and fail before network intent unless separately approved.

## 10. Information architecture

No new top-level destination.

- **Accounts → Commercial → Company:** coverage, watch policy, proposed-review strip, cited event feed, hiring history, mapping controls, and “Run company brief.”
- **Whitespace:** toggleable header overlay, off by default.
- **Signals/Today:** standard episode UI for convergence; at most one convergence item per account-target and one review-debt item per account.
- **Operations:** sync/freshness/evaluation measures and connection state.
- **Search/export/restore:** company entities, events, evidence, links, and watch policy follow the existing operational data contracts.

Both themes are first-class. Direction/status always pair color with text/glyph; age, expiry, unknown, and cross-hatch conventions remain unchanged.

## 11. Schema and API contract

Migrations are split to keep rebuilds reviewable:

- `0036_stage14_company_intel.sql`: entities/identifiers/account links/watch profiles; kinds; documents/spans; events/evidence; explicit-target links; hiring; sync runs/items; convergence/composition; integrity triggers and seed kinds.
- `0037_stage14_company_signals.sql`: rebuild `signal_episodes` to admit `source_kind='company'` and add persisted composition linkage where required.
- `0038_stage14_company_brief.sql`: rebuild `copilot_runs` to admit `intent='company_brief'` and recreate immutability triggers.

Core endpoints:

```text
GET/PUT  /api/accounts/{id}/company-watch
GET      /api/accounts/{id}/company
POST     /api/ingest/company-intel/sync
GET      /api/accounts/{id}/intel/feed
GET      /api/accounts/{id}/intel/overlay
GET      /api/accounts/{id}/intel/hiring
POST     /api/intel/events/{id}/confirm
POST     /api/intel/events/{id}/dismiss
POST     /api/intel/documents/{id}/retract
POST     /api/intel/events/{id}/links
POST     /api/intel/events/{id}/links/suggest
POST     /api/intel/events/{id}/links/{link_id}/confirm
POST     /api/intel/events/{id}/links/{link_id}/dismiss
POST     /api/accounts/{id}/intel/link-keywords
POST     /api/accounts/{id}/intel/evaluate
POST     /api/copilot/runs  (intent=company_brief)
```

Services own rules; routers remain thin. Every mutation audits through `repo`; all account-scoped tables carry standard soft deletion. Company records participate in account export/restore/search and Operations before Stage 14 is complete.

## 12. Delivery slices

**14.0 — foundation:** migration 0036, adapter fixtures, provider-scoped idempotent sync, proposal review, cited feed, Company sub-tab, watch policy, registry rows, audit and operations measures.

**14.1 — mapping/hiring/convergence:** explicit target links, outside-in overlay, posting-level hiring derivation, persisted convergence, signal episode bridge, contraction pacing guard, Today candidates.

**14.2 — brief:** copilot intent migration, scoped readers/allow-lists, fixed-section generation, packet/span citations, Company action, command classification, and golden/adversarial cases.

## 13. Definition of done and adversarial tests

On synthetic data, an operator can sync public artifacts, inspect exact evidence spans, review events, confirm links, see a non-invasive whitespace overlay, inspect a reproducible convergence episode, and run a fixed-section company brief with citations on every factual bullet.

Required tests:

- proposed events are excluded from overlay, convergence, brief packets, and Today at the query layer;
- confirmation without a live evidence span fails in API and trigger;
- provider-scoped duplicate IDs are idempotent while the same ID from another provider is allowed;
- ambiguous company identity is unmatched, never guessed;
- cross-account links and links with zero/multiple targets fail by trigger;
- same-kind, same-occurrence, same-origin, non-overlapping, or over-gap event pairs do not converge;
- convergence composition persists and episodes close after expiry, dismissal, retraction, or link loss;
- source correction/retraction invalidates an event with no remaining live evidence;
- each failed sync item rolls back independently without leaving a document, span, source reference, or derivative behind;
- one/stale/closed/duplicated/spread hiring postings do not cluster; five active unique postings in one function × region do, as proposed;
- contraction holds vendor-push candidates and never becomes an expansion positive;
- private-company missing filing coverage is insufficient; non-entailing and injection-bearing excerpts cannot change or pass the brief;
- immutable artifact/version and event-expiry rules are trigger-enforced;
- non-mock connection modes fail closed before network intent;
- no Stage 14 schema stores individual product usage, personal sentiment, or a numeric opportunity/intent score.

## 14. Explicit non-goals

Real fetching/scraping/provider integration; live LLM extraction; numeric opportunity/intent scoring; automatic whitespace/stakeholder edits; competitive battlecards; buyer web-visit tracking; personal sentiment; scheduled/pushed briefs; and client-facing intel outputs.
