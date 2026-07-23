"""Request models for v0.1 capture. Responses are plain dicts from DB rows.

Only v0.1 fields are accepted. Enums use Literal so bad values 422 at the edge.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Phase = Literal["foundation", "launch", "programmatic", "expansion", "renewal", "closed"]
Affiliation = Literal["client", "valence"]
Role = Literal[
    "champion", "budget_owner", "program_owner", "it", "legal_dpo",
    "works_council_contact", "other",
]
Stance = Literal["supporter", "skeptic", "unconverted"]
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


class StakeholderRoleCreate(BaseModel):
    program_id: str
    person_id: str
    role: Role = "other"
    stance: Optional[Stance] = None
    stance_assessed_on: Optional[str] = None
    stance_evidence_note: Optional[str] = None
    cares_about: Optional[str] = None
    value_for_them: Optional[str] = None


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
