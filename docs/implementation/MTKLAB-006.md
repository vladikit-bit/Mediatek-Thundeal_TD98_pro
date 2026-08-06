# Developer Specification: MTKLAB-006

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Implementation Details](#4-implementation-details)
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
Implement evidence deduplication in `src/mtklab/storage/db.py` when inserting records into the `evidences` table using `INSERT OR IGNORE`.

---

## 2. Files to Modify
1. `src/mtklab/storage/db.py`
2. `tests/test_storage.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/storage/db.py`
Update `store_evidence()`:
```python
def store_evidence(self, evidence: Evidence) -> bool:
    """Store evidence using INSERT OR IGNORE to prevent duplicate content hashes."""
    cursor = self._conn.execute(
        """
        INSERT OR IGNORE INTO evidences 
        (evidence_id, experiment_id, evidence_type, confidence, description, data_json, source_offset, source_size, tags_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence.evidence_id,
            evidence.experiment_id,
            evidence.evidence_type,
            evidence.confidence,
            evidence.description,
            json.dumps(evidence.data),
            evidence.source_offset,
            evidence.source_size,
            json.dumps(evidence.tags),
            evidence.created_at
        )
    )
    return cursor.rowcount > 0
```

---

## 4. Implementation Details

- Leverages primary key constraint on `evidences(evidence_id)`.
- `INSERT OR IGNORE` ensures existing content-addressed evidence records are preserved without throwing duplicate key errors.

---

## 5. Public API Changes

- `Database.store_evidence(evidence: Evidence) -> bool` return signature updated to return `True` if inserted, `False` if ignored as a duplicate.

---

## 6. Backward Compatibility Requirements

- Non-breaking storage layer enhancement. Existing evidence records are preserved intact.

---

## 7. Rollback Strategy

- Revert `store_evidence()` SQL query in `src/mtklab/storage/db.py` back to `INSERT INTO`.
- Revert unit tests in `tests/test_storage.py`.

---

## 8. Edge Cases & Validation

- Attempting to store the exact same `Evidence` object twice: Second call returns `False` without error or database corruption.
- Storing evidence with duplicate `evidence_id` but different timestamp: Duplicate `evidence_id` primary key ignores insert.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Unit test storing identical evidence twice -> second call returns `False` (ignored) without error.
  - Query database to confirm only 1 row exists for matching SHA-256 `evidence_id`.
- **Integration Tests**:
  - Run evidence creation concurrently/sequentially and confirm deduplication across experiments.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] Duplicate evidence inserts are safely ignored by `store_evidence()`.
- [ ] Primary key violations are prevented via `INSERT OR IGNORE`.
- [ ] Storage tests pass (`pytest tests/test_storage.py`).

---

## 11. Code Review Checklist

- [ ] `INSERT OR IGNORE` used cleanly in SQL query string.
- [ ] Rowcount boolean return value accurately reflects whether new record was stored.
- [ ] Unit tests verify deduplication on duplicate primary key collision.

---

## 12. Related Documents

- [ADR-002: Content-Addressed Evidence](../architecture/ADR/ADR-002-content-addressed-evidence.md)
- [MTKLAB-005 Specification](./MTKLAB-005.md)
