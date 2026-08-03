"""Request models for v0.1 capture. Responses are plain dicts from DB rows.

Only v0.1 fields are accepted. Enums use Literal so bad values 422 at the edge.
"""
from __future__ import annotations

from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    cadence_target_days: Optional[int] = None   # §3.6 per-role cadence override


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
    account_id: Optional[str] = None
    program_id: Optional[str] = None
    account_review_id: Optional[str] = None
    commitment_class: Literal["client", "leadership_to_operator", "operator_to_internal", "internal_peer"] = "client"
    description: str = Field(min_length=1)
    responsible_party_id: str            # required — who performs it
    internal_owner_id: str               # required — Valence follow-up owner
    due_date: str                        # required — 100% of commitments have a due date
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None

    @model_validator(mode="after")
    def commitment_context(self):
        if not self.account_id and not self.program_id:
            raise ValueError("account_id or program_id is required")
        return self


class DecisionCreate(BaseModel):
    account_id: Optional[str] = None
    program_id: Optional[str] = None
    account_review_id: Optional[str] = None
    description: str = Field(min_length=1)
    decided_on: Optional[str] = None
    decided_by_id: Optional[str] = None
    rationale: Optional[str] = None
    supersedes_id: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None

    @model_validator(mode="after")
    def decision_context(self):
        if not self.account_id and not self.program_id:
            raise ValueError("account_id or program_id is required")
        return self


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


class CommsSequenceCreate(BaseModel):
    program_id: str
    name: str = Field(min_length=1)
    purpose: Optional[str] = None
    moment_id: Optional[str] = None


class CommsSequenceCancel(BaseModel):
    reason: str = Field(min_length=1)


class CommsWaveCreate(BaseModel):
    moment_id: Optional[str] = None
    audience: Optional[str] = None
    message: str = Field(min_length=1)
    sender: Optional[str] = None
    channel: Optional[Channel] = None
    send_date: Optional[str] = None
    wave_number: int = Field(ge=1)
    follows_entry_id: Optional[str] = None
    offset_days: Optional[int] = Field(default=None, ge=0)
    segment_id: Optional[str] = None
    view_id: Optional[str] = None

    @model_validator(mode="after")
    def wave_shape(self):
        if self.segment_id and self.view_id:
            raise ValueError("use a segment or view, not both")
        if bool(self.follows_entry_id) != (self.offset_days is not None):
            raise ValueError("a predecessor and offset_days must be supplied together")
        return self


class CommsWavePatch(BaseModel):
    moment_id: Optional[str] = None
    audience: Optional[str] = None
    message: Optional[str] = Field(default=None, min_length=1)
    sender: Optional[str] = None
    channel: Optional[Channel] = None
    send_date: Optional[str] = None
    wave_number: Optional[int] = Field(default=None, ge=1)
    follows_entry_id: Optional[str] = None
    offset_days: Optional[int] = Field(default=None, ge=0)
    segment_id: Optional[str] = None
    view_id: Optional[str] = None


class CommsWaveSent(BaseModel):
    sent_at: Optional[str] = None


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
    # Stable population identity (Stage 5.5, §2). cohort_label is free text and cannot be
    # joined to a value target; these are what make the ledger computable. Optional, so
    # existing callers are unaffected — an observation without one simply isn't in the ledger.
    population_segment_id: Optional[str] = None
    population_view_id: Optional[str] = None


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
    definition_id,period_label,value[,program_id,population_segment_id,population_view_id,
    cohort_label,target,unit]"""
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
    amount: float = Field(ge=0)
    currency: Optional[str] = None
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


TriggerKind = Literal[
    "renewal_window", "overdue_commitment", "stale_stakeholder", "active_blocker",
    "checklist_overdue", "unanswered_email", "unidentified_placeholder", "cadence_overdue",
    "no_second_champion", "champion_gone_quiet", "stalled_cohort", "expansion_signal",
    "org_change_confirmed", "calendar_moment", "land_and_leave",
]


class PlayDefinitionCreate(BaseModel):
    name: str = Field(min_length=1)
    trigger_kind: TriggerKind
    action_template: str = Field(min_length=1)
    active: bool = True


class PlayEffectiveness(BaseModel):
    effectiveness: Literal["effective", "unclear", "ineffective"]
    effectiveness_note: Optional[str] = None


# --- Phase 3 Stage 5 — relationship intelligence -------------------------------

ChampionStage = Literal["identify", "develop", "validate", "arm", "maintain"]


class ChampionCandidateCreate(BaseModel):
    person_id: str
    program_id: Optional[str] = None
    stage: ChampionStage = "identify"
    notes: Optional[str] = None


class ChampionCandidatePatch(BaseModel):
    stage: Optional[ChampionStage] = None       # validate/arm/maintain gated by advocacy evidence
    developed_note: Optional[str] = None
    developed_on: Optional[str] = None
    armed_note: Optional[str] = None
    armed_on: Optional[str] = None
    notes: Optional[str] = None


class ExecPairingCreate(BaseModel):
    account_id: str
    valence_person_id: str
    client_person_id: str
    next_touch_planned: Optional[str] = None
    notes: Optional[str] = None


class ExecPairingPatch(BaseModel):
    valence_person_id: Optional[str] = None
    next_touch_planned: Optional[str] = None
    notes: Optional[str] = None


class MessagingEntryCreate(BaseModel):
    layer: Layer
    role: Optional[Role] = None
    value_prop: Optional[str] = None
    proof_points: Optional[str] = None
    objections: Optional[str] = None
    artifacts_note: Optional[str] = None
    visibility_class: VisibilityClass = "internal"


class MessagingEntryPatch(BaseModel):
    value_prop: Optional[str] = None
    proof_points: Optional[str] = None
    objections: Optional[str] = None
    artifacts_note: Optional[str] = None
    visibility_class: Optional[VisibilityClass] = None


class PullSignalCreate(BaseModel):
    account_id: str
    program_id: Optional[str] = None
    cell_id: Optional[str] = None
    signal_kind: Literal["client_pull", "champion_ask"] = "client_pull"
    requested_by_person_id: Optional[str] = None
    description: str = Field(min_length=1)
    occurred_on: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None


# --- Stage 5.5: whitespace map, value ledger, funding intelligence -------------------------
# (EXPANSION-ENGINE-SPEC.md §§1, 2, 4, 10)

Penetration = Literal["none", "pilot", "paid"]
EvidenceState = Literal["none", "anecdotal", "measured"]
BlockerState = Literal["clear", "gated"]
PursuitOutcome = Literal["none", "declined", "won", "deferred"]
BlockerLane = Literal["works_council", "it", "legal", "localization", "other"]
CellFact = Literal["penetration", "evidence_state", "blocker_state", "pursuit_outcome"]
TargetDirection = Literal["at_least", "at_most"]
TargetOrigin = Literal["scorecard", "business_case", "renewal", "expansion", "other"]
FundingPoolKind = Literal[
    "recovered_vendor_spend", "central_ld_budget", "chro_discretionary",
    "bu_cross_charge", "transformation_program", "other",
]
FundingPoolStatus = Literal["potential", "confirmed", "committed", "exhausted", "unavailable"]
PriceBasis = Literal["arr", "tcv", "one_time", "monthly"]
RevenueEventKind = Literal["expansion", "contraction", "churn", "renewal_flat", "price_change"]
HeadcountSourceKind = Literal["manual_entry", "hris_adapter", "client_stated", "estimate"]
AskStepKind = Literal[
    "business_case_delivered", "budget_owner_sponsorship", "budget_window",
    "procurement", "works_council", "signature", "other",
]


class AccountSettingsPut(BaseModel):
    min_cohort_size: int = Field(default=25, ge=1)
    pull_signal_window_days: int = Field(default=90, ge=1)
    signal_cooldown_days: int = Field(default=30, ge=0)
    signal_hysteresis_pct: float = Field(default=0.05, ge=0, lt=1)
    priority_response_hours: int = Field(default=24, ge=1)
    champion_quiet_days: int = Field(default=45, ge=1)
    business_timezone: str = Field(default="America/New_York", min_length=1)
    business_day_start_hour: int = Field(default=9, ge=0, le=23)
    business_day_end_hour: int = Field(default=17, ge=1, le=24)

    @field_validator("business_timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("must be an IANA timezone, for example America/New_York") from exc
        return value

    @model_validator(mode="after")
    def working_window_is_ordered(self):
        if self.business_day_end_hour <= self.business_day_start_hour:
            raise ValueError("business_day_end_hour must be after business_day_start_hour")
        return self


class CalendarEventCreate(BaseModel):
    account_id: str
    program_id: Optional[str] = None
    cell_id: Optional[str] = None
    purpose: Literal["kickoff", "governance", "qbr", "deployment_moment", "webinar",
                     "office_hours", "other"] = "other"
    title: str = Field(min_length=1)
    starts_at: str
    ends_at: Optional[str] = None
    location: Optional[str] = None
    organizer_email: Optional[str] = None


class CommsSessionCreate(BaseModel):
    comms_sequence_id: str
    invited_by_entry_id: Optional[str] = None
    purpose: Literal["webinar", "office_hours"]
    title: str = Field(min_length=1)
    starts_at: str
    ends_at: Optional[str] = None
    location: Optional[str] = None
    organizer_email: Optional[str] = None


class AttendeeRecord(BaseModel):
    person_id: Optional[str] = None
    name: Optional[str] = None
    email: str = Field(min_length=3)
    response_status: Literal["accepted", "declined", "tentative", "needs_action", "unknown"] = "unknown"
    attendance_status: Literal["invited", "attended", "no_show", "unknown"] = "unknown"
    attendance_scope: Literal["audience", "facilitator", "observer", "unknown"] = "unknown"


class SignalDismiss(BaseModel):
    reason: str = Field(min_length=1)


class OrgChangeAction(BaseModel):
    reason: Optional[str] = None
    actor: str = "operator"


class SuccessionComplete(BaseModel):
    successor_person_id: str
    transfer_note: Optional[str] = None


class AudienceTagCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    description: Optional[str] = None


class UseCaseCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    description: Optional[str] = None
    account_id: Optional[str] = None      # None = portfolio-global and cross-account comparable
    display_order: int = 0


class PartitionCreate(BaseModel):
    """The base partition is versioned: re-cutting it re-bases every historical number."""
    account_id: str
    basis: Optional[str] = None
    total_fte: Optional[int] = None
    fte_source: Optional[str] = None
    fte_as_of: Optional[str] = None
    reason: Optional[str] = None          # required by the API when superseding


class SegmentCreate(BaseModel):
    partition_id: str
    name: str = Field(min_length=1)
    business_unit: Optional[str] = None
    region: Optional[str] = None
    headcount: Optional[int] = Field(default=None, ge=0)
    headcount_source: Optional[str] = None
    headcount_as_of: Optional[str] = None
    paid_seats: Optional[int] = Field(default=None, ge=0)
    paid_seats_source: Optional[str] = None
    paid_seats_as_of: Optional[str] = None
    source_reference_id: Optional[str] = None
    is_unallocated: bool = False
    display_order: int = 0


class SegmentPatch(BaseModel):
    name: Optional[str] = None
    headcount: Optional[int] = Field(default=None, ge=0)
    headcount_source: Optional[str] = None
    headcount_as_of: Optional[str] = None
    paid_seats: Optional[int] = Field(default=None, ge=0)
    paid_seats_source: Optional[str] = None
    paid_seats_as_of: Optional[str] = None
    display_order: Optional[int] = None


class HeadcountObservationCreate(BaseModel):
    segment_id: str
    period_label: str = Field(min_length=1)
    headcount: int = Field(ge=0)
    source_kind: HeadcountSourceKind = "manual_entry"
    source_note: Optional[str] = None
    observed_on: str
    source_reference_id: Optional[str] = None


class PopulationViewCreate(BaseModel):
    """A composite ("DACH frontline managers"). Non-additive by construction."""
    account_id: str
    name: str = Field(min_length=1)
    segment_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    estimated_headcount: Optional[int] = Field(default=None, ge=0)
    headcount_source: Optional[str] = None
    headcount_as_of: Optional[str] = None


class CellCreate(BaseModel):
    account_id: str
    use_case_id: str
    segment_id: Optional[str] = None      # exactly one of segment_id / view_id
    view_id: Optional[str] = None
    estimated_seats: Optional[int] = Field(default=None, ge=0)
    paid_seats: int = Field(default=0, ge=0)
    sponsor_person_id: Optional[str] = None
    next_action: Optional[str] = None
    notes: Optional[str] = None
    client_visible: bool = False
    source_reference_id: Optional[str] = None


class CellPatch(BaseModel):
    """Non-state fields only. The four facts move through /set-fact, which requires a reason."""
    estimated_seats: Optional[int] = Field(default=None, ge=0)
    paid_seats: Optional[int] = Field(default=None, ge=0)
    sponsor_person_id: Optional[str] = None
    next_action: Optional[str] = None
    notes: Optional[str] = None
    client_visible: Optional[bool] = None
    source_reference_id: Optional[str] = None


class CellSetFact(BaseModel):
    """Cell states change only with a reason logged (§1.3)."""
    fact: CellFact
    value: str
    reason: str = Field(min_length=1)
    # pursuit_outcome=declined needs both; blocker_state=gated needs a lane.
    declined_on: Optional[str] = None
    blocker_lane: Optional[BlockerLane] = None
    blocker_owner_person_id: Optional[str] = None
    deferred_until: Optional[str] = None


class CellReopen(BaseModel):
    """A Declined cell reopens by an explicit event, not an edit (§1.3)."""
    reason: str = Field(min_length=1)
    reopened_on: Optional[str] = None


class CellEvidenceLink(BaseModel):
    object_type: Literal["value_story", "metric_observation"]
    object_id: str
    note: Optional[str] = None


class ValueTargetCreate(BaseModel):
    account_id: str
    definition_id: str
    segment_id: Optional[str] = None
    view_id: Optional[str] = None
    target_value: float
    unit: Optional[str] = None
    direction: TargetDirection = "at_least"
    timeframe_start: Optional[str] = None
    timeframe_end: str
    accepted_by_person_id: Optional[str] = None
    accepted_on: Optional[str] = None
    client_accepted: bool = False
    not_accepted_reason: Optional[str] = None
    origin: TargetOrigin = "scorecard"
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    notes: Optional[str] = None
    client_visible: bool = False


class ValueTargetSupersede(BaseModel):
    """A renegotiated bar supersedes; both stay readable."""
    target_value: float
    timeframe_end: str
    reason: str = Field(min_length=1)
    accepted_by_person_id: Optional[str] = None
    accepted_on: Optional[str] = None
    client_accepted: bool = False
    client_visible: bool = False


class ValueTargetEvidenceLink(BaseModel):
    object_type: Literal["value_story", "metric_observation"]
    object_id: str
    note: Optional[str] = None


class FundingPoolCreate(BaseModel):
    account_id: str
    name: str = Field(min_length=1)
    kind: FundingPoolKind = "other"
    owner_person_id: Optional[str] = None
    status: FundingPoolStatus = "potential"
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    recovered_spend_id: Optional[str] = None
    notes: Optional[str] = None
    client_visible: bool = False
    source_reference_id: Optional[str] = None


class FundingPoolPatch(BaseModel):
    name: Optional[str] = None
    status: Optional[FundingPoolStatus] = None
    owner_person_id: Optional[str] = None
    amount: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None
    client_visible: Optional[bool] = None
    source_reference_id: Optional[str] = None


class FiscalMapPut(BaseModel):
    fiscal_year_end: Optional[str] = None
    planning_window_start: Optional[str] = None
    planning_window_end: Optional[str] = None
    budget_request_deadline: Optional[str] = None
    procurement_lead_contract_id: Optional[str] = None
    works_council_lead_days: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    confirmed_on: Optional[str] = None
    confirmed_by: Optional[str] = None


class AskCalendarCreate(BaseModel):
    """Back-schedules the whole dependency chain from the target close date."""
    account_id: str
    name: str = Field(min_length=1)
    target_close_date: str
    opportunity_id: Optional[str] = None
    include_works_council: bool = True


class AskStepPatch(BaseModel):
    status: Optional[Literal["pending", "done", "late", "skipped"]] = None
    completed_on: Optional[str] = None
    owner_person_id: Optional[str] = None
    linked_type: Optional[Literal["task", "milestone", "compliance_item"]] = None
    linked_id: Optional[str] = None


class ContractRevenuePatch(BaseModel):
    """Revenue semantics on the contract. Describes what the canonical price MEANS; it does
    not overwrite the canonical copy."""
    currency: Optional[str] = None
    price_basis: Optional[PriceBasis] = None
    term_months: Optional[int] = Field(default=None, ge=1)


class RevenueEventCreate(BaseModel):
    account_id: str
    kind: RevenueEventKind
    effective_on: str
    contract_version_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    price_basis: Optional[PriceBasis] = None
    seats_delta: Optional[int] = None
    reason: Optional[str] = None
    source_reference_id: Optional[str] = None


# --- Phase 3 Stage 7.5: qualification, agreements, renewal, growth plan -------------------

class OpportunityQualificationPatch(BaseModel):
    value_target_id: Optional[str] = None
    budget_owner_person_id: Optional[str] = None
    ask_calendar_id: Optional[str] = None
    champion_person_id: Optional[str] = None
    program_id: Optional[str] = None


class OperationalAgreementCreate(BaseModel):
    account_id: str
    contract_version_id: str
    name: str = Field(min_length=1)
    source_kind: Literal["signed_paper", "agreed_conversation"]
    source_reference_id: Optional[str] = None
    source_interaction_id: Optional[str] = None
    value_target_id: str
    effective_on: str
    expires_on: Optional[str] = None
    seat_band_min: int = Field(gt=0)
    seat_band_max: int = Field(gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    agreed_process: str = Field(min_length=1)
    budget_owner_person_id: Optional[str] = None
    action_window_days: int = Field(default=14, gt=0)
    client_visible: bool = False
    notes: Optional[str] = None

    @model_validator(mode="after")
    def agreement_is_sourced_and_ordered(self):
        if self.source_kind == "signed_paper" and not self.source_reference_id:
            raise ValueError("signed-paper agreements require a source reference")
        if self.source_kind == "agreed_conversation" and not self.source_interaction_id:
            raise ValueError("conversation agreements require an interaction")
        if self.seat_band_max < self.seat_band_min:
            raise ValueError("seat_band_max must be at least seat_band_min")
        if self.currency and (len(self.currency) != 3 or self.currency != self.currency.upper()):
            raise ValueError("currency must be a three-letter uppercase ISO code")
        return self


class AgreementEventAction(BaseModel):
    dismissal_reason: Optional[str] = None


class GrowthPlanCreate(BaseModel):
    account_id: str
    name: str = Field(min_length=1)
    target_seats: int = Field(gt=0)
    target_date: str
    notes: Optional[str] = None


class GrowthPlanLineCreate(BaseModel):
    plan_id: str
    name: str = Field(min_length=1)
    segment_id: Optional[str] = None
    view_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    budget_owner_person_id: Optional[str] = None
    funding_pool_id: Optional[str] = None
    ask_calendar_id: Optional[str] = None
    cell_id: Optional[str] = None
    seat_count: int = Field(gt=0)
    seat_price_low: Optional[float] = Field(default=None, ge=0)
    seat_price_high: Optional[float] = Field(default=None, ge=0)
    seat_price_currency: Optional[str] = None
    seat_price_basis: Optional[Literal["annual_recurring", "term_total", "one_time"]] = None
    probability: float = Field(default=0.5, ge=0, le=1)
    probability_author: str = Field(default="operator", min_length=1)
    probability_assessed_on: str
    ask_date: Optional[str] = None
    status: Literal["planned", "committed", "funded", "slipped", "declined"] = "planned"
    client_visible: bool = False
    source_reference_id: Optional[str] = None
    competitive_notes: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def line_population_and_price_are_valid(self):
        if bool(self.segment_id) == bool(self.view_id):
            raise ValueError("exactly one of segment_id or view_id is required")
        if (self.seat_price_low is not None and self.seat_price_high is not None
                and self.seat_price_high < self.seat_price_low):
            raise ValueError("seat_price_high must be at least seat_price_low")
        if self.client_visible and not self.source_reference_id:
            raise ValueError("shared growth-plan lines require a source reference")
        return self


class GrowthPlanLinePatch(BaseModel):
    status: Optional[Literal["planned", "committed", "funded", "slipped", "declined"]] = None
    seat_count: Optional[int] = Field(default=None, gt=0)
    probability: Optional[float] = Field(default=None, ge=0, le=1)
    probability_author: Optional[str] = Field(default=None, min_length=1)
    probability_assessed_on: Optional[str] = None
    ask_date: Optional[str] = None
    client_visible: Optional[bool] = None
    source_reference_id: Optional[str] = None
    notes: Optional[str] = None
    cell_id: Optional[str] = None
    seat_price_currency: Optional[str] = None
    seat_price_basis: Optional[Literal["annual_recurring", "term_total", "one_time"]] = None


# Stage 9 — the playbook records what actually carried a dated cell transition.  Shape tags
# are optional because base segments may not have an audience tag; the global use case remains
# the minimum comparable shape.
class PlaybookEntryCreate(BaseModel):
    transition_history_id: str
    motion_run: str = Field(min_length=1)
    evidence_summary: Optional[str] = None
    message_summary: Optional[str] = None
    message_layer: Optional[Layer] = None
    motion_started_on: Optional[str] = None
    what_worked: Optional[str] = None
    what_differently: Optional[str] = None
    tag_ids: list[str] = Field(default_factory=list)


class PlaybookPlayPromotion(BaseModel):
    name: str = Field(min_length=1)
    action_template: str = Field(min_length=1)


class PlaybookMessagePromotion(BaseModel):
    role: Optional[str] = None
    value_prop: Optional[str] = None
    proof_points: Optional[str] = None
    objections: Optional[str] = None
    artifacts_note: Optional[str] = None


# --- Internal operating layer -------------------------------------------------

class ForecastPeriodCreate(BaseModel):
    name: str = Field(min_length=1)
    starts_on: str
    ends_on: str
    cadence: Literal["weekly", "monthly", "quarterly", "annual", "custom"]
    scenario_type: str = "operating"
    timezone: str = "America/New_York"


class ForecastEntryCreate(BaseModel):
    account_id: str
    opportunity_id: Optional[str] = None
    contract_version_id: Optional[str] = None
    category: Literal["commit", "best_case", "pipeline", "omitted"] = "pipeline"
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    price_basis: Optional[PriceBasis] = None
    probability: Optional[float] = Field(default=None, ge=0, le=1)
    probability_rationale: Optional[str] = None
    amount_rationale: Optional[str] = None
    assessed_on: str
    expected_decision_date: Optional[str] = None
    help_needed_note: Optional[str] = None
    renewal_budget_owner_person_id: Optional[str] = None
    renewal_position: Optional[Literal["confirmed_intent", "commercial_review", "procurement_in_progress", "unknown"]] = None
    unresolved_conditions: Optional[str] = None
    omitted_reason: Optional[str] = None

    @model_validator(mode="after")
    def one_target_and_units(self):
        if bool(self.opportunity_id) == bool(self.contract_version_id):
            raise ValueError("exactly one forecast target is required")
        if self.currency and (len(self.currency) != 3 or self.currency != self.currency.upper()):
            raise ValueError("currency must be a three-letter uppercase code")
        if self.probability is not None and not self.probability_rationale:
            raise ValueError("probability_rationale is required with probability")
        return self


class ForecastEntryPatch(BaseModel):
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    price_basis: Optional[PriceBasis] = None
    probability: Optional[float] = Field(default=None, ge=0, le=1)
    probability_rationale: Optional[str] = None
    amount_rationale: Optional[str] = None
    assessed_on: Optional[str] = None
    expected_decision_date: Optional[str] = None
    help_needed_note: Optional[str] = None
    renewal_budget_owner_person_id: Optional[str] = None
    renewal_position: Optional[Literal["confirmed_intent", "commercial_review", "procurement_in_progress", "unknown"]] = None
    unresolved_conditions: Optional[str] = None


class ForecastCategoryChange(BaseModel):
    category: Literal["commit", "best_case", "pipeline", "omitted"]
    driver: str = Field(min_length=1)
    omitted_reason: Optional[str] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    corrects_event_id: Optional[str] = None


class ForecastSourceCreate(BaseModel):
    interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    growth_plan_line_id: Optional[str] = None
    revenue_event_id: Optional[str] = None
    ask_calendar_id: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def one_source(self):
        if sum(bool(x) for x in (self.interaction_id, self.source_reference_id,
                                 self.growth_plan_line_id, self.revenue_event_id,
                                 self.ask_calendar_id)) != 1:
            raise ValueError("exactly one typed source is required")
        return self


class RenewalOutcomeCreate(BaseModel):
    account_id: str
    contract_version_id: str
    outcome: Literal["renewed", "churned", "deferred", "unresolved"]
    occurred_on: str
    actual_amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    price_basis: Optional[PriceBasis] = None
    source_reference_id: Optional[str] = None
    note: Optional[str] = None


class ReportRedOriginExclusionCreate(BaseModel):
    report_kind: Literal["monthly_portfolio_brief"] = "monthly_portfolio_brief"
    origin_type: Literal["risk", "issue", "status_assessment", "escalation", "internal_ask", "attention_item"]
    origin_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expires_on: str


class InternalAskCreate(BaseModel):
    need: str = Field(min_length=1)
    success_condition: str = Field(min_length=1)
    ask_type: Literal["general", "data_request", "product", "legal", "deal_desk", "executive", "pricing"] = "general"
    requested_by_person_id: str
    requested_from_person_id: Optional[str] = None
    requested_from_function_id: Optional[str] = None
    current_owner_person_id: Optional[str] = None
    needed_by: str
    opportunity_id: Optional[str] = None
    forecast_entry_id: Optional[str] = None
    account_review_id: Optional[str] = None
    generated_document_id: Optional[str] = None
    feedback_occurrence_id: Optional[str] = None
    revenue_amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    price_basis: Optional[PriceBasis] = None
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    metric_definition: Optional[str] = None
    population_context: Optional[str] = None
    requested_cohort_or_period: Optional[str] = None
    requested_current_through: Optional[str] = None
    expected_delivery_format: Optional[str] = None

    @model_validator(mode="after")
    def requested_from_target(self):
        if not self.requested_from_person_id and not self.requested_from_function_id:
            raise ValueError("a requested-from person or function is required")
        return self


class InternalAskStatus(BaseModel):
    status: Literal["acknowledged", "in_progress", "delivered", "declined", "raised"]
    reason: Optional[str] = None
    delivered_on: Optional[str] = None
    completion_note: Optional[str] = None
    result_source_reference_id: Optional[str] = None


class EscalationCreate(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    default_id: Optional[str] = None


class EscalationEventCreate(BaseModel):
    event_type: Literal["raised", "response", "advanced", "resolved", "note"]
    destination_person_id: Optional[str] = None
    destination_function_id: Optional[str] = None
    threshold_reason: Optional[str] = None
    response: Optional[str] = None


class EscalationDefaultPatch(BaseModel):
    path_type: Optional[Literal["functional", "hierarchical"]] = None
    threshold_business_hours: Optional[int] = Field(default=None, ge=0)
    destination_function_id: Optional[str] = None
    destination_role: Optional[str] = None
    expected_response_hours: Optional[int] = Field(default=None, gt=0)
    next_step: Optional[str] = None


class InternalSettingsPatch(BaseModel):
    operator_identity: Optional[str] = Field(default=None, min_length=1)
    business_timezone: Optional[str] = None
    business_day_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    business_day_end_hour: Optional[int] = Field(default=None, ge=1, le=24)
    working_weekdays_json: Optional[str] = None

    @field_validator("business_timezone")
    @classmethod
    def internal_timezone_exists(cls, value):
        if value:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("unknown IANA timezone") from exc
        return value

    @field_validator("working_weekdays_json")
    @classmethod
    def weekdays_are_iso_numbers(cls, value):
        if value is not None:
            import json
            try:
                days = json.loads(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("working_weekdays_json must be a JSON array") from exc
            if not isinstance(days, list) or not days or any(not isinstance(x, int) or x < 1 or x > 7 for x in days):
                raise ValueError("working weekdays must be ISO weekday numbers 1 through 7")
        return value


class AccountReviewCreate(BaseModel):
    review_type: Literal["weekly", "monthly", "quarterly", "ad_hoc"] = "quarterly"
    scheduled_on: Optional[str] = None
    chair_person_id: Optional[str] = None
    participant_ids: list[str] = Field(default_factory=list)


class AccountReviewHold(BaseModel):
    held_on: str
    source_interaction_id: str


class OperatorViewCreate(BaseModel):
    body: str = Field(min_length=1)
    assessed_on: str


class StatusAssessmentCreate(BaseModel):
    dimension: Literal["delivery", "commercial"]
    value: Literal["on_track", "at_risk", "off_track", "unknown"]
    rationale: Optional[str] = None
    criteria_version_id: Optional[str] = None
    recovery_owner_person_id: Optional[str] = None
    recovery_action: Optional[str] = None
    recovery_due_on: Optional[str] = None
    leadership_ask_id: Optional[str] = None
    leadership_not_applicable_reason: Optional[str] = None
    assessed_on: str


class StatusCriteriaCreate(BaseModel):
    account_id: Optional[str] = None
    dimension: Literal["delivery", "commercial"]
    green_criteria: str = Field(min_length=1)
    amber_criteria: str = Field(min_length=1)
    red_criteria: str = Field(min_length=1)
    unknown_criteria: str = Field(min_length=1)
    effective_on: str
    source_note: Optional[str] = None


class RosterCreate(BaseModel):
    person_id: str
    role: Literal["account_lead", "supporting_em", "advisor", "executive_sponsor", "data_partner", "product_partner", "legal_partner", "support_partner", "other"]
    standing_responsibilities: str = Field(min_length=1)
    coverage_type: Literal["primary", "backup"] = "primary"
    active_from: str
    active_through: Optional[str] = None
    expected_touch_cadence_days: Optional[int] = Field(default=None, gt=0)
    briefing_scope: Optional[str] = None
    notes: Optional[str] = None


class FeedbackItemCreate(BaseModel):
    title: str = Field(min_length=1)
    problem_statement: str = Field(min_length=1)
    feedback_type: Literal["feature", "workflow", "integration", "localization", "reporting", "other"] = "feature"
    owner_function_id: Optional[str] = None
    owner_person_id: Optional[str] = None


class FeedbackOccurrenceCreate(BaseModel):
    account_id: str
    stakeholder_person_id: str
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    source_span: Optional[str] = None
    forecast_entry_id: Optional[str] = None
    growth_plan_line_id: Optional[str] = None
    workaround: Optional[str] = None
    impact: Optional[str] = None
    captured_on: str


class FeedbackStatus(BaseModel):
    status: Literal["logged", "submitted", "roadmapped", "shipped", "declined"]
    reason: str = Field(min_length=1)
    product_reference: Optional[str] = None


class FeedbackTouchCreate(BaseModel):
    touch_type: Literal["acknowledgment", "resolution"]
    interaction_id: str


class FeedbackOccurrenceMove(BaseModel):
    feedback_item_id: str
    reason: str = Field(min_length=1)


# --- Stage 11: adoption campaigns (ADOPTION-CAMPAIGN-SPEC.md) --------------------------------

EvaluationDesign = Literal["descriptive", "pre_post", "comparator"]
BarrierCategory = Literal["capability", "opportunity", "motivation", "unknown"]
BarrierConfidence = Literal["observed", "reported", "hypothesis"]
InterventionKind = Literal[
    "enablement", "workflow_embed", "champion_action", "communication",
    "reinforcement", "discovery",
]
CampaignTargetRole = Literal["primary", "secondary", "guardrail"]
CompletionOutcome = Literal[
    "target_met", "improved_not_met", "no_demonstrated_change", "regressed", "inconclusive",
]


class CampaignCreate(BaseModel):
    account_id: str
    program_id: str
    use_case_id: str
    name: str = Field(min_length=1)
    target_behavior: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    planned_start_on: str
    planned_end_on: str
    internal_owner_person_id: str
    # Exactly one cohort; the model enforces it so the DB CHECK is a backstop, not the message.
    segment_id: Optional[str] = None
    view_id: Optional[str] = None
    cell_id: Optional[str] = None
    evaluation_on: Optional[str] = None
    evaluation_design: EvaluationDesign = "descriptive"
    client_sponsor_person_id: Optional[str] = None
    lead_champion_person_id: Optional[str] = None
    created_from_signal_episode_id: Optional[str] = None
    diagnosis_source_reference_id: Optional[str] = None
    diagnosis_source_interaction_id: Optional[str] = None

    @model_validator(mode="after")
    def _one_cohort(self):
        if bool(self.segment_id) == bool(self.view_id):
            raise ValueError("a campaign targets exactly one population: segment_id or view_id")
        return self


class CampaignPatch(BaseModel):
    """Draft content only. Status moves through the dedicated transition endpoints."""
    name: Optional[str] = None
    target_behavior: Optional[str] = None
    hypothesis: Optional[str] = None
    planned_start_on: Optional[str] = None
    planned_end_on: Optional[str] = None
    evaluation_on: Optional[str] = None
    evaluation_design: Optional[EvaluationDesign] = None
    client_sponsor_person_id: Optional[str] = None
    lead_champion_person_id: Optional[str] = None
    baseline_gap_reason: Optional[str] = None
    sponsor_gap_reason: Optional[str] = None
    concurrent_intervention_reason: Optional[str] = None
    already_met_reason: Optional[str] = None


class CampaignTransition(BaseModel):
    reason: str = Field(min_length=1)
    actor: Optional[str] = None
    # pause/cancel/complete carry their own required detail
    pause_reason: Optional[str] = None
    resume_condition: Optional[str] = None
    cancel_reason: Optional[str] = None
    completion_outcome: Optional[CompletionOutcome] = None
    completion_reviewed_on: Optional[str] = None
    completion_note: Optional[str] = None


class CampaignBarrierCreate(BaseModel):
    category: BarrierCategory
    description: str = Field(min_length=1)
    observed_on: str
    confidence: BarrierConfidence = "hypothesis"
    is_primary: bool = False
    source_reference_id: Optional[str] = None
    source_interaction_id: Optional[str] = None

    @model_validator(mode="after")
    def _needs_source(self):
        if not (self.source_reference_id or self.source_interaction_id):
            raise ValueError("a barrier needs a dated source: reference or interaction")
        return self


class CampaignBarrierPatch(BaseModel):
    state: Optional[Literal["open", "addressed", "ruled_out"]] = None
    resolution_note: Optional[str] = None
    is_primary: Optional[bool] = None


class CampaignTargetCreate(BaseModel):
    value_target_id: str
    role: CampaignTargetRole = "primary"
    comparator_segment_id: Optional[str] = None
    comparator_view_id: Optional[str] = None

    @model_validator(mode="after")
    def _one_comparator(self):
        if self.comparator_segment_id and self.comparator_view_id:
            raise ValueError("a comparator is one population: segment or view, not both")
        return self


class CampaignPlanLinkCreate(BaseModel):
    intervention_kind: InterventionKind
    sequence: int = 0
    purpose: Optional[str] = None
    cue: Optional[str] = None
    is_reinforcement: bool = False
    intended_barrier_id: Optional[str] = None
    task_id: Optional[str] = None
    commitment_id: Optional[str] = None
    milestone_id: Optional[str] = None
    comms_entry_id: Optional[str] = None
    deployment_moment_id: Optional[str] = None
    calendar_event_id: Optional[str] = None
    generated_document_id: Optional[str] = None
    messaging_entry_id: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_link(self):
        links = [self.task_id, self.commitment_id, self.milestone_id, self.comms_entry_id,
                 self.deployment_moment_id, self.calendar_event_id,
                 self.generated_document_id, self.messaging_entry_id]
        if sum(1 for x in links if x) != 1:
            raise ValueError("a plan item links exactly one existing record")
        return self


class CampaignCheckpointCreate(BaseModel):
    scheduled_on: str
    next_evidence_on: Optional[str] = None


class CampaignCheckpointHold(BaseModel):
    held_on: str
    assessment: Literal["on_track", "at_risk", "unknown"]
    decision: Literal["continue", "adjust", "pause", "complete"]
    reason: str = Field(min_length=1)
    observations_reviewed: list[str] = Field(default_factory=list)
    source_interaction_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    next_evidence_on: Optional[str] = None


class CampaignFromEpisode(BaseModel):
    """Convert a signal episode to a DRAFT campaign (§7.1). Never ready, never active."""
    name: Optional[str] = None
    target_behavior: Optional[str] = None
    hypothesis: Optional[str] = None
    planned_start_on: str
    planned_end_on: str
    evaluation_on: Optional[str] = None
    internal_owner_person_id: str
    program_id: Optional[str] = None
    segment_id: Optional[str] = None
    view_id: Optional[str] = None
    use_case_id: Optional[str] = None
    evaluation_design: EvaluationDesign = "comparator"   # §5.2 default for signal-triggered work


class CampaignAttachEpisode(BaseModel):
    campaign_id: str


class PlanLinkSupersede(BaseModel):
    replacement_link_id: str
    reason: str = Field(min_length=1)
    checkpoint_id: Optional[str] = None


# --- Stage 11.2: campaign learning (ADOPTION-CAMPAIGN-SPEC.md §§8-9) ----------------------------
class RetrospectiveInterventionIn(BaseModel):
    plan_link_id: str = Field(min_length=1)
    verdict: Literal["appeared_to_help", "appeared_not_to_help", "failed", "skipped", "unclear"]
    note: str = Field(min_length=1)


class CampaignRetrospectiveCreate(BaseModel):
    barrier_actually_present: Literal["capability", "opportunity", "motivation",
                                      "mixed", "none_found", "unknown"]
    barrier_note: str = Field(min_length=1)
    what_to_reuse: str = Field(min_length=1)
    what_to_change: str = Field(min_length=1)
    follow_on: Literal["none", "repeat_same_cohort", "different_cohort",
                       "different_intervention", "escalate", "stop"] = "none"
    follow_on_note: Optional[str] = None
    messaging_entry_id: Optional[str] = None
    reviewed_on: str
    author: Optional[str] = None
    interventions: list[RetrospectiveInterventionIn] = Field(default_factory=list)


# --- Stage 12: Account Copilot ---------------------------------------------------------------
class CopilotRunCreate(BaseModel):
    scope_type: Literal["program", "account", "portfolio"]
    account_id: Optional[str] = None
    program_id: Optional[str] = None
    query_text: str = Field(min_length=1, max_length=1200)
    intent: Optional[Literal["fact", "synthesis", "changes", "weekly", "draft"]] = None
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=200)
    context_run_id: Optional[str] = None


class CopilotFeedbackCreate(BaseModel):
    claim_id: Optional[str] = None
    run_source_id: Optional[str] = None
    issue_kind: Literal[
        "helpful", "partially_helpful", "unhelpful", "wrong_fact", "missing_source",
        "wrong_source", "stale_or_superseded_source", "scope_error", "unsafe_wording",
        "style_mismatch",
    ]
    note: Optional[str] = Field(default=None, max_length=2000)
    actor: Optional[str] = None


class CopilotDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=180)


class WritingStyleProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    audience: Literal["internal", "client_facing"]
    rules: dict = Field(default_factory=dict)
    sample_text: Optional[str] = Field(default=None, max_length=5000)
    effective_on: str
    author: str = Field(min_length=1, max_length=120)
    supersedes_id: Optional[str] = None


class CopilotConfigurationCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    model_version: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=120)
    retrieval_version: str = Field(min_length=1, max_length=120)
    validator_version: str = Field(min_length=1, max_length=120)


class CopilotReplayCreate(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=100)


class CopilotConfigurationEvaluation(BaseModel):
    run_ids_by_case: dict[str, str]


class CopilotFeedbackReviewCreate(BaseModel):
    disposition: Literal["confirmed", "dismissed", "canonical_record_updated", "evaluation_backlog"]
    resolution_note: str = Field(min_length=1, max_length=2000)
    reviewed_by: str = Field(min_length=1, max_length=120)


class CopilotEntityAliasCreate(BaseModel):
    account_id: Optional[str] = None
    record_type: Literal["person", "program", "population_segment", "population_view"]
    record_id: str = Field(min_length=1)
    alias: str = Field(min_length=1, max_length=120)
    created_by: str = Field(min_length=1, max_length=120)
