# Developer Specification: MTKLAB-007

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Database Migration & SQL](#4-database-migration--sql)
- [5. Public API Changes](#5-public-api-changes)
- [6. Backward Compatibility Requirements](#6-backward-compatibility-requirements)
- [7. Rollback Strategy](#7-rollback-strategy)
- [8. Edge Cases & Validation](#8-edge-cases--validation)
- [9. Testing Requirements](#9-testing-requirements)
- [10. Acceptance Criteria & Definition of Done](#10-acceptance-criteria--definition-of-done)
- [11. Code Review Checklist](#11-code-review-checklist)
- [12. Related Documents](#12-related-documents)

---

## 1. Objective
Add database schema migration `003_junctions.sql` to create normalized junction tables `finding_evidences` and `hypothesis_evidences` for explicit relational linkages.

---

## 2. Files to Modify
1. `src/mtklab/storage/migrations/003_junctions.sql` (New file)
2. `tests/test_storage.py`

---

## 3. Code Locations & Changes

Create `src/mtklab/storage/migrations/003_junctions.sql`:
```sql
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
```

---

## 4. Database Migration & SQL

- Establishes relational integrity for Many-to-Many finding-to-evidence and hypothesis-to-evidence relationships.
- Adds foreign key cascades and secondary indexes for reverse lookups.

---

## 5. Public API Changes

- None (database schema migration layer only).

---

## 6. Backward Compatibility Requirements

- Non-destructive migration. Leaves existing `findings.evidence_ids_json` columns untouched.

---

## 7. Rollback Strategy

- Drop tables `finding_evidences` and `hypothesis_evidences`.
- Remove migration file `003_junctions.sql`.

---

## 8. Edge Cases & Validation

- Foreign key constraint failure if invalid `finding_id` or `evidence_id` referenced (when PRAGMA foreign_keys = ON).
- Duplicate junction pair (`finding_id`, `evidence_id`): Caught by composite PRIMARY KEY.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Verify migration `003_junctions.sql` executes cleanly on database initialization.
  - Test foreign key constraints on `finding_evidences` and `hypothesis_evidences`.
- **Integration Tests**:
  - Run full migration pipeline (`001`, `002`, `003`) on fresh and populated databases.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `003_junctions.sql` migration creates junction tables and indexes.
- [ ] Primary key and foreign key constraints function properly.
- [ ] Database tests pass cleanly (`pytest tests/test_storage.py`).

---

## 11. Code Review Checklist

- [ ] SQLite syntax valid and includes `IF NOT EXISTS`.
- [ ] Foreign keys configure `ON DELETE CASCADE`.
- [ ] Index creation statements present for performant queries.

---

## 12. Related Documents

- [RFC Document](../architecture/RFC.md#5-system-invariants)
- [ADR-004: SQLite Schema Evolution](../architecture/ADR/ADR-004-sqlite-schema-evolution.md)
- [MTKLAB-006 Specification](./MTKLAB-006.md)
