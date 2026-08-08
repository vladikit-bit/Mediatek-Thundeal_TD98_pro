-- Migration 003: Create junction tables for normalized evidence links
CREATE TABLE IF NOT EXISTS finding_evidences (
    finding_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (finding_id, evidence_id),
    FOREIGN KEY (finding_id) REFERENCES findings(finding_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidences(evidence_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_finding_evidences_finding ON finding_evidences(finding_id);
CREATE INDEX IF NOT EXISTS idx_finding_evidences_evidence ON finding_evidences(evidence_id);

CREATE TABLE IF NOT EXISTS hypothesis_evidences (
    hypothesis_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    link_type TEXT CHECK(link_type IN ('SUPPORTING', 'CONTRADICTING')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (hypothesis_id, evidence_id),
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidences(evidence_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_evidences_hyp ON hypothesis_evidences(hypothesis_id);
