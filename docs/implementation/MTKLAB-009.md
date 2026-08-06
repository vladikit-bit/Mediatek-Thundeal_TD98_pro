# Developer Specification: MTKLAB-009

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
Add database schema migration `004_runs.sql` to introduce `runs` and `experiment_runs` tables for session execution tracking.

---

## 2. Files to Modify
1. `src/mtklab/storage/migrations/004_runs.sql` (New file)
2. `tests/test_storage.py`

---

## 3. Code Locations & Changes

Create `src/mtklab/storage/migrations/004_runs.sql`:
```sql
-- Migration 004: Create runs and experiment_runs tracking tables
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    command TEXT,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    experiment_run_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    duration_seconds REAL,
    metrics_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_run_id ON experiment_runs(run_id);
```

---

## 4. Database Migration & SQL

- Provides tabular schema for capturing execution session metadata and per-experiment outcomes.

---

## 5. Public API Changes

- None (database migration file creation).

---

## 6. Backward Compatibility Requirements

- Non-breaking additive migration. Existing tables remain unaffected.

---

## 7. Rollback Strategy

- Drop tables `experiment_runs` and `runs`.
- Remove `004_runs.sql` migration file.

---

## 8. Edge Cases & Validation

- Foreign key constraint on `experiment_runs(run_id)` requires valid parent `run_id` in `runs` table when foreign keys enabled.
- Status string values (`SUCCESS`, `FAILED`, `CANCELLED`, `RUNNING`) unconstrained at DB level for flexibility, validated in Python application layer.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Verify migration `004_runs.sql` applies cleanly on database initialization.
  - Test inserting and querying `runs` and `experiment_runs` records.
- **Integration Tests**:
  - Execute full sequence of migrations (`001` through `004`) and verify schema integrity.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `004_runs.sql` creates `runs` and `experiment_runs` tables.
- [ ] Primary key and foreign key constraints function properly.
- [ ] Database storage tests pass cleanly (`pytest tests/test_storage.py`).

---

## 11. Code Review Checklist

- [ ] SQLite schema uses `IF NOT EXISTS`.
- [ ] Foreign key `ON DELETE CASCADE` specified for `run_id`.
- [ ] Index created on `experiment_runs.run_id`.

---

## 12. Related Documents

- [RFC Document](../architecture/RFC.md#31-identity-management)
- [ADR-001: Execution Run Tracking Model](../architecture/ADR/ADR-001-runs-and-executions.md)
- [ADR-004: SQLite Schema Evolution](../architecture/ADR/ADR-004-sqlite-schema-evolution.md)
- [MTKLAB-008 Specification](./MTKLAB-008.md)
