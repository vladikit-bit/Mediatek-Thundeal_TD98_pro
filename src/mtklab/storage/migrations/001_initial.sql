-- 001_initial.sql
-- Initializes the basic schema for the MT5889 Reverse Engineering Laboratory Evidence Database

CREATE TABLE experiments (
    experiment_id     TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    version           TEXT NOT NULL,
    status            TEXT NOT NULL,          -- success|partial|failed
    started_at        TIMESTAMP NOT NULL,
    completed_at      TIMESTAMP,
    summary           TEXT,
    parameters_json   TEXT NOT NULL,
    metadata_json     TEXT NOT NULL,
    errors_json       TEXT NOT NULL
);

CREATE TABLE evidences (
    evidence_id       TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL REFERENCES experiments(experiment_id),
    evidence_type     TEXT NOT NULL,
    confidence        TEXT NOT NULL,          -- CANDIDATE, PROBABLE, VERIFIED
    description       TEXT NOT NULL,
    data_json         TEXT NOT NULL,
    source_offset     INTEGER,
    source_size       INTEGER,
    tags_json         TEXT NOT NULL,
    timestamp         TIMESTAMP NOT NULL
);

CREATE INDEX idx_evidences_experiment ON evidences(experiment_id);
CREATE INDEX idx_evidences_offset ON evidences(source_offset);
CREATE INDEX idx_evidences_type ON evidences(evidence_type);

CREATE TABLE findings (
    finding_id        TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL REFERENCES experiments(experiment_id),
    kind              TEXT NOT NULL,
    offset            INTEGER NOT NULL,
    size              INTEGER,
    confidence        TEXT NOT NULL,
    label             TEXT,
    description       TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    metadata_json     TEXT NOT NULL,
    versions_json     TEXT NOT NULL
);

CREATE INDEX idx_findings_offset ON findings(offset);
CREATE INDEX idx_findings_kind ON findings(kind);
CREATE INDEX idx_findings_confidence ON findings(confidence);

CREATE TABLE hypotheses (
    hypothesis_id     TEXT PRIMARY KEY,
    subject_offset    INTEGER NOT NULL,
    subject_size      INTEGER,
    claim             TEXT NOT NULL,
    alternative_claims_json TEXT NOT NULL,
    status            TEXT NOT NULL,
    supporting_evidence_json TEXT NOT NULL,
    contradicting_evidence_json TEXT NOT NULL,
    resolved_claim    TEXT,
    resolution_reason TEXT NOT NULL,
    confidence        TEXT NOT NULL,
    versions_json     TEXT NOT NULL
);

CREATE INDEX idx_hypotheses_offset ON hypotheses(subject_offset);

CREATE TABLE experiment_artifacts (
    artifact_id       TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL REFERENCES experiments(experiment_id),
    artifact_type     TEXT NOT NULL,
    file_path         TEXT NOT NULL,
    description       TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL
);

CREATE INDEX idx_experiment_artifacts_exp ON experiment_artifacts(experiment_id);
