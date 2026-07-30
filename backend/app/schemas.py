"""Request models for v0.1 capture. Responses are plain dicts from DB rows.

Only v0.1 fields are accepted. Enums use Literal so bad values 422 at the edge.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Phase = Literal["foundation", "launch", "programmatic", "expansion", "renewal", "closed"]
Affiliation = Literal["client", "valence"]
Role = Literal[
    # original set (kept for back-compat)
    "champion", "budget_owner", "program_owner", "it", "legal_dpo",
    "works_council_contact", "other",
    # §3.2 full buying committee
    "executive_sponsor", "financial_gatekeeper", "procurement", "technical_evaluator",
    "legal_compliance", "end_user_voice", "coach", "detractor",
]
Layer = Literal["executive", "economic", "operational", "technical_gating", "user_advocate"]
Stance = Literal["supporter", "skeptic", "unconverted"]
AdvocacyKind = Literal[
    "advocacy_without_us", "secured_meeting", "defended_us", "presented_internally", "other",
]
InteractionType = Literal["call", "meeting", "email", "workshop", "message", "other"]
SourceType = Literal[
    "file", "transcript_span", "meeting", "crm_record", "data_report", "manual_entry",
]


class AccountCreate(BaseModel):
    name: str = Field(min_length=1)
    short_context: Optional[str] = None
    incumbent_note: Optional[str] = None


class AccountPatch(BaseModel):
    name: Optional[str] = None
    short_context: Optional[str] = None
    incumbent_note: Optional[str] = None


class ProgramCreate(BaseModel):
    account_id: str
    name: str = Field(min_length=1)
    phase: Phase = "foundation"
    region: Optional[str] = None
    audience: Optional[str] = None
    use_case: Optional[str] = None
    problem_statement: Optional[str] = None
    in_scope_population: Optional[str] = None
    out_of_scope_population: Optional[str] = None
    launch_definition: Optional[str] = None
    success_criteria: Optional[str] = None
    expansion_hypothesis: Optional[str] = None
    explicit_exclusions: Optional[str] = None
    sponsor_person_id: Optional[str] = None


class ProgramPatch(BaseModel):
    name: Optional[str] = None
    phase: Optional[Phase] = None
    region: Optional[str] = None
    audience: Optional[str] = None
    use_case: Optional[str] = None
    problem_statement: Optional[str] = None
    in_scope_population: Optional[str] = None
    out_of_scope_population: Optional[str] = None
    launch_definition: Optional[str] = None
    success_criteria: Optional[str] = None
    expansion_hypothesis: Optional[str] = None
    explicit_exclusions: Optional[str] = None
    sponsor_person_id: Optional[str] = None


class PersonCreate(BaseModel):
    name: str = Field(min_length=1)
    affiliation: Affiliation = "client"
    account_id: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None


class PersonPatch(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    account_id: Optional[str] = None
    comms_preference: Optional[str] = None   # professional observation only (D-76)
    metric_judged_on: Optional[str] = None


class StakeholderRoleCreate(BaseModel):
    program_id: str
    person_id: str
    role: Role = "other"
    layer: Optional[Layer] = None
    stance: Optional[Stance] = None
    stance_assessed_on: Optional[str] = None
    stance_evidence_note: Optional[str] = None
    cares_about: Optional[str] = None
    value_for_them: Optional[str] = None


class StakeholderRolePatch(BaseModel):
    role: Optional[Role] = None
    layer: Optional[Layer] = None
    stance: Optional[Stance] = None
    stance_assessed_on: Optional[str] = None
    stance_evidence_note: Optional[str] = None
    cares_about: Optional[str] = None
    value_for_them: Optional[str] = None


class AdvocacyEventCreate(BaseModel):
    person_id: str
    program_id: Optional[str] = None
    kind: AdvocacyKind
    occurred_on: Optional[str] = None
    note: Optional[str] = None
    source_reference_id: Optional[str] = None


class InteractionCreate(BaseModel):
    account_id: str
    program_id: Optional[str] = None       # nullable (G2)
    occurred_on: Optional[str] = None      # defaults to today (UTC) if omitted
    occurred_at_time: Optional[str] = None
    type: InteractionType = "meeting"
    summary: Optional[str] = None
    raw_notes: Optional[str] = None
    source_reference_id: Optional[str] = None
    follow_up: Optional[str] = None
    meaningful_touch: bool = True
    participant_ids: list[str] = Field(default_factory=list)
    # Ambiguous notes dropped straight to the capture inbox — no classification at capture time.
    inbox_notes: list[str] = Field(default_factory=list)


class SourceReferenceCreate(BaseModel):
    type: SourceType = "manual_entry"
    label: str = Field(min_length=1)
    url: Optional[str] = None
    locator: Optional[str] = None
    tags: Optional[str] = None          # comma-separated (Section 5O)


class SourceReferencePatch(BaseModel):
    label: Optional[str] = None
    url: Optional[str] = None
    locator: Optional[str] = None
    tags: Optional[str] = None


# --- v0.2 execution objects ---------------------------------------------------

Severity = Literal["low", "medium", "high"]
ExecTarget = Literal["task", "commitment", "decision", "risk", "issue"]


class TaskCreate(BaseModel):
    program_id: str
    description: str = Field(min_length=1)
    internal_owner_id: Optional[str] = None
    due_date: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None


class CommitmentCreate(BaseModel):
    program_id: str
    description: str = Field(min_length=1)
    responsible_party_id: str            # required — who performs it
    internal_owner_id: str               # required — Valence follow-up owner
    due_date: str                        # required — 100% of commitments have a due date
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None


class DecisionCreate(BaseModel):
    program_id: str
    description: str = Field(min_length=1)
    decided_on: Optional[str] = None
    decided_by_id: Optional[str] = None
    rationale: Optional[str] = None
    supersedes_id: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None


class RiskCreate(BaseModel):
    program_id: str
    description: str = Field(min_length=1)
    severity: Severity = "medium"
    is_blocker: bool = False
    mitigation: Optional[str] = None
    internal_owner_id: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None


class IssueCreate(BaseModel):
    program_id: str
    description: str = Field(min_length=1)
    is_blocker: bool = False
    internal_owner_id: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None


class MilestoneCreate(BaseModel):
    program_id: str
    name: str = Field(min_length=1)
    target_date: Optional[str] = None
    success_criteria: Optional[str] = None
    at_risk: bool = False
    source_interaction_id: Optional[str] = None


# --- transitions (closure rules from Section 4 "definitions of done") ---

class CommitmentClose(BaseModel):
    acknowledged_by_id: Optional[str] = None   # the receiving party who acknowledged
    closed_on: Optional[str] = None
    close_note: Optional[str] = None


class TaskClose(BaseModel):
    status: Literal["done", "cancelled"] = "done"
    closed_on: Optional[str] = None
    close_note: Optional[str] = None


class RiskClose(BaseModel):
    close_reason: Literal["no_longer_possible", "no_longer_relevant"]
    closed_on: Optional[str] = None
    close_note: Optional[str] = None


class IssueResolve(BaseModel):
    resolution_type: Literal["condition_removed", "workaround_operating"]
    resolved_on: Optional[str] = None
    resolution_note: Optional[str] = None


class MilestoneComplete(BaseModel):
    completed_on: Optional[str] = None
    completion_note: Optional[str] = None


StatusValue = Literal["on_track", "at_risk", "off_track", "unknown"]
StatusDimension = Literal["delivery", "commercial"]


class AccountStatusUpdate(BaseModel):
    dimension: StatusDimension
    value: StatusValue
    rationale: Optional[str] = None
    change_condition: Optional[str] = None
    assessed_on: Optional[str] = None   # defaults to today


class QueueSnooze(BaseModel):
    item_key: str
    snooze_until: Optional[str] = None
    resurface_condition: Optional[str] = None


class QueueResolve(BaseModel):
    item_key: str
    successor_action_type: Literal["task", "commitment"]
    successor_action_id: str


class InboxConvert(BaseModel):
    """Convert an untriaged inbox item into one execution object, no retype.
    program_id defaults to the source interaction's program; payload carries the
    target-specific fields (description pre-filled by the UI from raw_text).
    """
    target_type: ExecTarget
    payload: dict


# --- v1 commercial & deployment ------------------------------------------------

BudgetState = Literal["conceptually_supported", "in_planning", "formally_allocated",
                      "requisition_created", "procurement_approved", "executed"]
Outcome = Literal["won", "lost", "deferred", "merged", "no_decision"]


class ExpansionCreate(BaseModel):
    account_id: str
    name: str = Field(min_length=1)
    use_case: Optional[str] = None
    target_seats: Optional[int] = None
    expected_value: Optional[float] = None
    sponsor_person_id: Optional[str] = None
    budget_owner_person_id: Optional[str] = None
    funding_source: Optional[str] = None
    supporting_evidence: Optional[str] = None
    decision_date: Optional[str] = None
    budget_state: BudgetState = "conceptually_supported"
    blockers: Optional[str] = None
    next_action: Optional[str] = None
    source_interaction_id: Optional[str] = None


class ExpansionPatch(BaseModel):
    name: Optional[str] = None
    use_case: Optional[str] = None
    target_seats: Optional[int] = None
    expected_value: Optional[float] = None
    sponsor_person_id: Optional[str] = None
    budget_owner_person_id: Optional[str] = None
    funding_source: Optional[str] = None
    supporting_evidence: Optional[str] = None
    decision_date: Optional[str] = None
    budget_state: Optional[BudgetState] = None
    blockers: Optional[str] = None
    next_action: Optional[str] = None


class ExpansionClose(BaseModel):
    outcome: Outcome
    outcome_reason: str = Field(min_length=1)


class ContractCreate(BaseModel):
    account_id: str
    version_label: str = Field(min_length=1)
    seats: Optional[int] = None
    price: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    renewal_date: Optional[str] = None
    notice_period_days: Optional[int] = None
    procurement_lead_days: Optional[int] = None
    amendments: Optional[str] = None
    source_system: Optional[str] = "crm"
    source_identifier: Optional[str] = None
    editable_locally: bool = False
    supersedes_id: Optional[str] = None


class ContractOverlay(BaseModel):
    overlay_expected_decision_date: str
    overlay_rationale: str = Field(min_length=1)


class PhaseGateCreate(BaseModel):
    program_id: str
    name: str = Field(min_length=1)
    gates_phase: Optional[Phase] = None
    items: list[str] = Field(default_factory=list)   # initial checklist descriptions


class GateItemToggle(BaseModel):
    complete: bool


class GateWaive(BaseModel):
    waiver_reason: str = Field(min_length=1)


MomentType = Literal["talent_calendar", "manager_workflow", "business_event",
                     "proactive_coaching", "comms_campaign"]
IntegrationStatus = Literal["not_started", "in_progress", "live", "not_applicable"]


class MomentCreate(BaseModel):
    program_id: str
    name: str = Field(min_length=1)
    type: MomentType = "business_event"
    client_owner_person_id: Optional[str] = None
    comms_hook: Optional[str] = None
    integration_status: IntegrationStatus = "not_started"
    event_date: Optional[str] = None
    outcome: Optional[str] = None


Channel = Literal["teams", "web", "slack", "mobile", "email", "other"]


class CommsCreate(BaseModel):
    program_id: str
    moment_id: Optional[str] = None
    audience: Optional[str] = None
    message: Optional[str] = None
    sender: Optional[str] = None
    channel: Optional[Channel] = None
    send_date: Optional[str] = None
    status: Literal["planned", "sent", "cancelled"] = "planned"


ComplianceLane = Literal["it_security", "legal_dpo", "works_council", "channel_setup",
                         "localization_qa", "trust_comms", "hr_boundary"]
ComplianceStatus = Literal["not_started", "in_progress", "complete", "blocked", "not_applicable"]


class ComplianceCreate(BaseModel):
    program_id: str
    lane: ComplianceLane
    region: Optional[str] = None
    status: ComplianceStatus = "not_started"
    owner_person_id: Optional[str] = None
    notes: Optional[str] = None


class CompliancePatch(BaseModel):
    status: Optional[ComplianceStatus] = None
    owner_person_id: Optional[str] = None
    notes: Optional[str] = None


class ScopeChangeCreate(BaseModel):
    program_id: str
    description: str = Field(min_length=1)
    agreed_by_person_id: Optional[str] = None
    changed_on: Optional[str] = None
    source_interaction_id: Optional[str] = None


class GovernancePatch(BaseModel):
    governance_steering: Optional[str] = None
    governance_rhythm: Optional[str] = None
    next_qbr_date: Optional[str] = None


# --- v2 data & evidence --------------------------------------------------------

EvidenceTier = Literal["anecdote", "client_quote", "measured_operational", "correlated_business"]
VisibilityClass = Literal["internal", "client_working", "qbr_exec", "externally_referenceable"]


class MetricDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    meaning: Optional[str] = None
    source_system: Optional[str] = "Valence Data team"
    owner: Optional[str] = None
    version: str = "1"
    population: Optional[str] = None
    formula_notes: Optional[str] = None
    stale_after_days: int = 30


class MetricObservationCreate(BaseModel):
    definition_id: str
    definition_version: str = "1"
    program_id: Optional[str] = None
    cohort_label: Optional[str] = None
    period_label: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    target: Optional[float] = None
    current_through: Optional[str] = None
    source_reference_id: Optional[str] = None


class BenchmarkCreate(BaseModel):
    name: str = Field(min_length=1)
    value: Optional[float] = None
    unit: Optional[str] = None
    population: str = Field(min_length=1)   # required — benchmarks are never population-less
    period: str = Field(min_length=1)       # required
    source: str = Field(min_length=1)       # required
    version: str = "1"


class ValueStoryCreate(BaseModel):
    outcome: str = Field(min_length=1)
    account_id: Optional[str] = None
    program_id: Optional[str] = None
    tags: Optional[str] = None
    evidence_tier: EvidenceTier = "anecdote"
    visibility_class: VisibilityClass = "internal"   # safe default: internal-only
    identifiable: bool = False
    is_negative: bool = False
    source_reference_id: Optional[str] = None


class MetricImport(BaseModel):
    """CSV import for metric observations. Columns:
    definition_id,period_label,value[,program_id,cohort_label,target,unit]"""
    source_label: Optional[str] = None
    current_through: Optional[str] = None
    csv_text: str


# --- v3 visualization ----------------------------------------------------------

Influence = Literal["low", "medium", "high"]
RelStrength = Literal["weak", "medium", "strong"]
EdgeType = Literal["reports_to", "sponsors", "influences"]


class GraphAssessment(BaseModel):
    """Setting influence / relationship strength requires a date + evidence note
    (stakeholder assessments are personal data, Section 2)."""
    influence: Optional[Influence] = None
    relationship_strength: Optional[RelStrength] = None
    graph_assessed_on: Optional[str] = None
    graph_evidence_note: Optional[str] = None


class EdgeCreate(BaseModel):
    account_id: str
    from_person_id: str
    to_person_id: str
    type: EdgeType
    program_id: Optional[str] = None
    note: Optional[str] = None


class MapPromote(BaseModel):
    """Promote / demote an execution object onto the client-facing mutual action plan."""
    object_type: Literal["commitment", "task", "milestone"]
    object_id: str
    client_visible: bool


class RecoveredSpendCreate(BaseModel):
    account_id: str
    label: str = Field(min_length=1)
    amount: float
    source_note: Optional[str] = None


# --- v4 AI & automation --------------------------------------------------------

class ExtractionRequest(BaseModel):
    transcript: str = Field(min_length=1)
    account_id: str
    program_id: Optional[str] = None
    interaction_id: Optional[str] = None
    backend: Optional[Literal["mock", "api"]] = None   # override the configured default


class ManualExtractionRequest(BaseModel):
    """The operator ran their own local LLM and pastes its JSON output here."""
    account_id: str
    program_id: Optional[str] = None
    interaction_id: Optional[str] = None
    proposals_json: str = Field(min_length=1)          # raw JSON from the local model


class ProposalAccept(BaseModel):
    # optional per-item field overrides before applying (e.g. add owners/due date)
    overrides: dict = Field(default_factory=dict)


TriggerKind = Literal["renewal_window", "overdue_commitment", "stale_stakeholder", "active_blocker"]


class PlayDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    trigger_kind: TriggerKind
    action_template: str = Field(min_length=1)
    active: bool = True


class PlayEffectiveness(BaseModel):
    effectiveness: Literal["effective", "unclear", "ineffective"]
    effectiveness_note: Optional[str] = None
