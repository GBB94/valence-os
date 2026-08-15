-- Migration 0028 — Internal Ops Stages 10.2, 10.4, and 10.5 ledgers.
PRAGMA foreign_keys = ON;

CREATE TABLE internal_functions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT INTO internal_functions(id,name,created_at,updated_at) VALUES
 ('function-data','Data',datetime('now'),datetime('now')),
 ('function-product','Product',datetime('now'),datetime('now')),
 ('function-legal','Legal',datetime('now'),datetime('now')),
 ('function-deal-desk','Deal Desk',datetime('now'),datetime('now')),
 ('function-finance-pricing','Finance/Pricing',datetime('now'),datetime('now')),
 ('function-executive-sponsor','Executive Sponsor',datetime('now'),datetime('now')),
 ('function-support','Support',datetime('now'),datetime('now')),
 ('function-other','Other',datetime('now'),datetime('now'));

CREATE TABLE internal_asks (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    need TEXT NOT NULL,
    success_condition TEXT NOT NULL,
    ask_type TEXT NOT NULL DEFAULT 'general' CHECK (ask_type IN
      ('general','data_request','product','legal','deal_desk','executive','pricing')),
    requested_by_person_id TEXT NOT NULL REFERENCES persons(id),
    requested_from_person_id TEXT REFERENCES persons(id),
    requested_from_function_id TEXT REFERENCES internal_functions(id),
    current_owner_person_id TEXT REFERENCES persons(id),
    needed_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'raised' CHECK (status IN ('raised','acknowledged','in_progress','delivered','declined')),
    opportunity_id TEXT REFERENCES expansion_opportunities(id),
    forecast_entry_id TEXT REFERENCES forecast_entries(id),
    account_review_id TEXT REFERENCES account_reviews(id),
    generated_document_id TEXT REFERENCES generated_documents(id),
    feedback_occurrence_id TEXT REFERENCES product_feedback_occurrences(id),
    revenue_amount REAL CHECK (revenue_amount IS NULL OR revenue_amount>=0),
    currency TEXT CHECK (currency IS NULL OR (length(currency)=3 AND currency=upper(currency))),
    price_basis TEXT CHECK (price_basis IS NULL OR price_basis IN ('arr','tcv','one_time','monthly')),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id TEXT REFERENCES source_references(id),
    decline_reason TEXT,
    delivered_on TEXT,
    delivered_by TEXT,
    completion_note TEXT,
    result_source_reference_id TEXT REFERENCES source_references(id),
    metric_definition TEXT,
    population_context TEXT,
    requested_cohort_or_period TEXT,
    requested_current_through TEXT,
    expected_delivery_format TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK (requested_from_person_id IS NOT NULL OR requested_from_function_id IS NOT NULL),
    CHECK (status<>'declined' OR decline_reason IS NOT NULL),
    CHECK (status<>'delivered' OR (delivered_on IS NOT NULL AND delivered_by IS NOT NULL AND (completion_note IS NOT NULL OR result_source_reference_id IS NOT NULL)))
);
CREATE INDEX idx_internal_asks_account ON internal_asks(account_id,status,needed_by);
CREATE INDEX idx_internal_asks_function ON internal_asks(requested_from_function_id,status);

CREATE TABLE internal_ask_events (
    id TEXT PRIMARY KEY,
    ask_id TEXT NOT NULL REFERENCES internal_asks(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('created','acknowledged','started','delivered','declined','reopened','note')),
    status_before TEXT,
    status_after TEXT,
    reason TEXT,
    actor TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_internal_ask_events ON internal_ask_events(ask_id,occurred_at);
CREATE TRIGGER trg_internal_ask_events_update BEFORE UPDATE ON internal_ask_events BEGIN SELECT RAISE(ABORT,'ask events are append-only'); END;
CREATE TRIGGER trg_internal_ask_events_delete BEFORE DELETE ON internal_ask_events BEGIN SELECT RAISE(ABORT,'ask events are append-only'); END;

CREATE TABLE internal_ask_documents (
    ask_id TEXT NOT NULL REFERENCES internal_asks(id),
    document_id TEXT NOT NULL REFERENCES generated_documents(id),
    relationship TEXT NOT NULL DEFAULT 'blocked',
    created_at TEXT NOT NULL,
    PRIMARY KEY(ask_id,document_id)
);

CREATE TABLE escalation_defaults (
    id TEXT PRIMARY KEY,
    ask_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    path_type TEXT NOT NULL CHECK (path_type IN ('functional','hierarchical')),
    threshold_business_hours INTEGER NOT NULL CHECK (threshold_business_hours>=0),
    destination_function_id TEXT REFERENCES internal_functions(id),
    destination_role TEXT,
    expected_response_hours INTEGER NOT NULL CHECK (expected_response_hours>0),
    next_step TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    UNIQUE(ask_type,severity)
);
INSERT INTO escalation_defaults
(id,ask_type,severity,path_type,threshold_business_hours,destination_function_id,destination_role,expected_response_hours,next_step,created_at,updated_at)
VALUES
('esc-general-medium','general','medium','functional',16,'function-other',NULL,8,'Escalate to the accountable leader with dated facts.',datetime('now'),datetime('now')),
('esc-data-high','data_request','high','functional',8,'function-data',NULL,4,'Escalate to Data leadership and restate the blocked deliverable.',datetime('now'),datetime('now')),
('esc-product-medium','product','medium','functional',16,'function-product',NULL,8,'Escalate to the Product owner with account evidence.',datetime('now'),datetime('now')),
('esc-legal-high','legal','high','functional',8,'function-legal',NULL,4,'Escalate to Legal leadership with the decision deadline.',datetime('now'),datetime('now')),
('esc-deal-high','deal_desk','high','hierarchical',8,'function-deal-desk','revenue_leader',4,'Escalate the commercial tradeoff to the revenue leader.',datetime('now'),datetime('now')),
('esc-exec-high','executive','high','hierarchical',8,'function-executive-sponsor','executive_sponsor',4,'Escalate to the executive sponsor with a proposed action.',datetime('now'),datetime('now')),
('esc-pricing-high','pricing','high','hierarchical',8,'function-finance-pricing','pricing_approver',4,'Escalate the pricing decision and explicit tradeoffs.',datetime('now'),datetime('now'));

CREATE TABLE escalation_instances (
    id TEXT PRIMARY KEY,
    ask_id TEXT NOT NULL REFERENCES internal_asks(id),
    default_id TEXT REFERENCES escalation_defaults(id),
    severity TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    path_type TEXT NOT NULL CHECK (path_type IN ('functional','hierarchical')),
    threshold_business_hours INTEGER NOT NULL,
    destination_function_id TEXT REFERENCES internal_functions(id),
    destination_role TEXT,
    expected_response_hours INTEGER NOT NULL,
    next_step TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    opened_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    resolved_at TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK (status<>'resolved' OR (resolved_at IS NOT NULL AND resolution IS NOT NULL))
);
CREATE INDEX idx_escalations_ask ON escalation_instances(ask_id,status);

CREATE TABLE escalation_events (
    id TEXT PRIMARY KEY,
    escalation_id TEXT NOT NULL REFERENCES escalation_instances(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('raised','response','advanced','resolved','note')),
    destination_person_id TEXT REFERENCES persons(id),
    destination_function_id TEXT REFERENCES internal_functions(id),
    threshold_reason TEXT,
    response TEXT,
    actor TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_escalation_events ON escalation_events(escalation_id,occurred_at);
CREATE TRIGGER trg_escalation_events_update BEFORE UPDATE ON escalation_events BEGIN SELECT RAISE(ABORT,'escalation events are append-only'); END;
CREATE TRIGGER trg_escalation_events_delete BEFORE DELETE ON escalation_events BEGIN SELECT RAISE(ABORT,'escalation events are append-only'); END;

CREATE TABLE roster_role_defaults (
    role TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    default_responsibilities TEXT,
    default_touch_cadence_days INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT INTO roster_role_defaults(role,label,created_at,updated_at) VALUES
 ('account_lead','Account lead',datetime('now'),datetime('now')),
 ('supporting_em','Supporting EM',datetime('now'),datetime('now')),
 ('advisor','Advisor',datetime('now'),datetime('now')),
 ('executive_sponsor','Executive sponsor',datetime('now'),datetime('now')),
 ('data_partner','Data partner',datetime('now'),datetime('now')),
 ('product_partner','Product partner',datetime('now'),datetime('now')),
 ('legal_partner','Legal partner',datetime('now'),datetime('now')),
 ('support_partner','Support partner',datetime('now'),datetime('now')),
 ('other','Other',datetime('now'),datetime('now'));

CREATE TABLE account_internal_roster (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    person_id TEXT NOT NULL REFERENCES persons(id),
    role TEXT NOT NULL REFERENCES roster_role_defaults(role),
    standing_responsibilities TEXT NOT NULL,
    coverage_type TEXT NOT NULL DEFAULT 'primary' CHECK (coverage_type IN ('primary','backup')),
    active_from TEXT NOT NULL,
    active_through TEXT,
    expected_touch_cadence_days INTEGER CHECK (expected_touch_cadence_days IS NULL OR expected_touch_cadence_days>0),
    briefing_scope TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK (active_through IS NULL OR active_through>=active_from)
);
CREATE UNIQUE INDEX idx_roster_live ON account_internal_roster(account_id,person_id,role) WHERE archived=0;

CREATE TABLE product_feedback_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('feature','workflow','integration','localization','reporting','other')),
    owner_function_id TEXT REFERENCES internal_functions(id),
    owner_person_id TEXT REFERENCES persons(id),
    status TEXT NOT NULL DEFAULT 'logged' CHECK (status IN ('logged','submitted','roadmapped','shipped','declined')),
    product_reference TEXT,
    status_rationale TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK (status<>'declined' OR status_rationale IS NOT NULL),
    CHECK (status<>'shipped' OR product_reference IS NOT NULL)
);

CREATE TABLE product_feedback_occurrences (
    id TEXT PRIMARY KEY,
    feedback_item_id TEXT NOT NULL REFERENCES product_feedback_items(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    stakeholder_person_id TEXT NOT NULL REFERENCES persons(id),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id TEXT REFERENCES source_references(id),
    source_span TEXT,
    forecast_entry_id TEXT REFERENCES forecast_entries(id),
    growth_plan_line_id TEXT REFERENCES growth_plan_lines(id),
    workaround TEXT,
    impact TEXT,
    captured_by TEXT NOT NULL,
    captured_on TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK (source_interaction_id IS NOT NULL OR source_reference_id IS NOT NULL)
);
CREATE INDEX idx_feedback_occurrence_item ON product_feedback_occurrences(feedback_item_id,account_id);

CREATE TABLE product_feedback_events (
    id TEXT PRIMARY KEY,
    feedback_item_id TEXT NOT NULL REFERENCES product_feedback_items(id),
    occurrence_id TEXT REFERENCES product_feedback_occurrences(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('status_changed','occurrence_moved','note')),
    value_before TEXT,
    value_after TEXT,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER trg_feedback_events_update BEFORE UPDATE ON product_feedback_events BEGIN SELECT RAISE(ABORT,'feedback events are append-only'); END;
CREATE TRIGGER trg_feedback_events_delete BEFORE DELETE ON product_feedback_events BEGIN SELECT RAISE(ABORT,'feedback events are append-only'); END;

CREATE TABLE product_feedback_touches (
    id TEXT PRIMARY KEY,
    occurrence_id TEXT NOT NULL REFERENCES product_feedback_occurrences(id),
    touch_type TEXT NOT NULL CHECK (touch_type IN ('acknowledgment','resolution')),
    interaction_id TEXT NOT NULL REFERENCES interactions(id),
    recorded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(occurrence_id,touch_type)
);

-- Typed feedback link becomes enforceable now that the target exists.
CREATE TRIGGER trg_internal_ask_feedback_scope BEFORE INSERT ON internal_asks
WHEN NEW.feedback_occurrence_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM product_feedback_occurrences o WHERE o.id=NEW.feedback_occurrence_id AND o.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'ask feedback occurrence belongs to a different account'); END;
CREATE TRIGGER trg_internal_ask_scope BEFORE INSERT ON internal_asks
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.requested_by_person_id AND p.affiliation='valence')
 OR (NEW.requested_from_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.requested_from_person_id AND p.affiliation='valence'))
 OR (NEW.current_owner_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.current_owner_person_id AND p.affiliation='valence'))
 OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.forecast_entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM forecast_entries e WHERE e.id=NEW.forecast_entry_id AND e.account_id=NEW.account_id))
 OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
 OR (NEW.generated_document_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM generated_documents d WHERE d.id=NEW.generated_document_id AND d.account_id=NEW.account_id))
 OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'internal ask link is outside its account or Valence roster'); END;
CREATE TRIGGER trg_roster_valence_insert BEFORE INSERT ON account_internal_roster
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'roster members must be Valence people'); END;
CREATE TRIGGER trg_feedback_occurrence_scope BEFORE INSERT ON product_feedback_occurrences
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.stakeholder_person_id AND p.account_id=NEW.account_id)
 OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
 OR (NEW.forecast_entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM forecast_entries f WHERE f.id=NEW.forecast_entry_id AND f.account_id=NEW.account_id))
 OR (NEW.growth_plan_line_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM growth_plan_lines g WHERE g.id=NEW.growth_plan_line_id AND g.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'feedback occurrence link belongs to a different account'); END;
CREATE TRIGGER trg_feedback_owner_valence BEFORE INSERT ON product_feedback_items
WHEN NEW.owner_person_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM persons p WHERE p.id=NEW.owner_person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'feedback owner must be a Valence person'); END;
CREATE TRIGGER trg_escalation_event_valence BEFORE INSERT ON escalation_events
WHEN NEW.destination_person_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM persons p WHERE p.id=NEW.destination_person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'escalation destination must be a Valence person'); END;
CREATE TRIGGER trg_feedback_touch_scope BEFORE INSERT ON product_feedback_touches
WHEN NOT EXISTS (SELECT 1 FROM product_feedback_occurrences o JOIN interactions i ON i.id=NEW.interaction_id WHERE o.id=NEW.occurrence_id AND i.account_id=o.account_id)
BEGIN SELECT RAISE(ABORT,'feedback touch interaction belongs to a different account'); END;
CREATE TRIGGER trg_status_leadership_ask_scope BEFORE INSERT ON account_status_assessments
WHEN NEW.leadership_ask_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM internal_asks a WHERE a.id=NEW.leadership_ask_id AND a.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'status leadership ask belongs to a different account'); END;
CREATE TRIGGER trg_status_assessment_immutable_update BEFORE UPDATE ON account_status_assessments
BEGIN SELECT RAISE(ABORT,'status assessments are append-only'); END;
CREATE TRIGGER trg_status_assessment_immutable_delete BEFORE DELETE ON account_status_assessments
BEGIN SELECT RAISE(ABORT,'status assessments are append-only'); END;
