# Developer Specification: MTKLAB-001

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Database Migration & SQL](#4-database-migration--sql)
- [5. Backward Compatibility & Rollback](#5-backward-compatibility--rollback)
- [6. Edge Cases & Validation](#6-edge-cases--validation)
- [7. Testing Requirements](#7-testing-requirements)
- [8. Acceptance Criteria & Definition of Done](#8-acceptance-criteria--definition-of-done)
- [9. Related Documents](#9-related-documents)

---

## 1. Objective
Add database schema migration `002_logical_ids.sql` to introduce the `logical_id` column to the `findings` table, fix the `INSERT OR REPLACE` anti-pattern in `Database` storage methods to prevent foreign key cascade deletions, and update the `Finding` dataclass to include `logical_id`.

---

## 2. Files to Modify
1. `src/mtklab/storage/migrations/002_logical_ids.sql` (New file)
2. `src/mtklab/core/evidence.py`
3. `src/mtklab/storage/db.py`
4. `tests/test_storage.py` (or new migration test)

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/core/evidence.py`
- Modify `Finding` dataclass:
  - Add optional `logical_id: Optional[str] = None` field.
  - Update `to_dict()` and `from_dict()` serialization methods to handle `logical_id`.

### 3.2 `src/mtklab/storage/db.py`
- Replace `INSERT OR REPLACE INTO evidences` with `INSERT OR IGNORE INTO evidences`.
- Update `store_finding()` SQL query to include `logical_id` column insertion.
- Update `get_findings()` row mapping to populate `logical_id`.

---

## 4. Database Migration & SQL

Create `src/mtklab/storage/migrations/002_logical_ids.sql`:
```sql
-- Migration 002: Add logical_id column to findings table
ALTER TABLE findings ADD COLUMN logical_id TEXT;
CREATE INDEX IF NOT EXISTS idx_findings_logical_id ON findings(logical_id);
```

---

## 5. Backward Compatibility & Rollback

- **Backward Compatibility**: Existing databases automatically apply migration `002`. Existing findings without `logical_id` will have `NULL` values until re-processed.
- **Rollback Strategy**:
  - Delete `002_logical_ids.sql` migration file.
  - Revert changes to `db.py` and `evidence.py`.

---

## 6. Edge Cases & Validation

- **Null Logical ID**: Querying existing finding records with `NULL` `logical_id` must return gracefully with `logical_id=None`.
- **Duplicate Insertion Safeguard**: `INSERT OR IGNORE` on `evidences` prevents constraint violation exceptions during concurrent experiment execution.

---

## 7. Testing Requirements

- **Unit Tests**: Test `Finding.to_dict()` and `from_dict()` with and without `logical_id`.
- **Migration Tests**: Verify applying `002_logical_ids.sql` on a version 1 database adds the column and index correctly.
- **Integration Test**: Verify `store_finding()` persists and retrieves `logical_id`.

---

## 8. Acceptance Criteria & Definition of Done

- [ ] `002_logical_ids.sql` migration creates `logical_id` column and index on `findings`.
- [ ] `db.py` uses `INSERT OR IGNORE` for `evidences` storage.
- [ ] `Finding` object serializes and deserializes `logical_id`.
- [ ] All unit and migration tests pass (`PYTHONPATH=src pytest`).

---

## 9. Related Documents

- [RFC Document](../architecture/RFC.md)
- [Issue Backlog Card](../architecture/ISSUE_BACKLOG.md#mtklab-001-add-002_logical_idssql-migration--storage-fixes)
- [ADR-003: Logical ID Deduplication](../architecture/ADR/ADR-003-logical-id-deduplication.md)
- [ADR-004: SQLite Schema Evolution](../architecture/ADR/ADR-004-sqlite-schema-evolution.md)
