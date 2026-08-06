# Developer Specification: MTKLAB-003

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
Implement database lookup and upsert query methods in `src/mtklab/storage/db.py` to retrieve the latest version of a finding by `logical_id` and store updated version snapshots without violating constraints.

---

## 2. Files to Modify
1. `src/mtklab/storage/db.py`
2. `tests/test_storage.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/storage/db.py`
Add method `get_latest_finding_by_logical_id()`:
```python
def get_latest_finding_by_logical_id(self, logical_id: str) -> Optional[Finding]:
    """Retrieve the highest version finding for a given logical_id."""
    cursor = self._conn.execute(
        """
        SELECT * FROM findings 
        WHERE logical_id = ? 
        ORDER BY versions_json DESC LIMIT 1
        """,
        (logical_id,)
    )
    row = cursor.fetchone()
    return self._row_to_finding(row) if row else None
```

Update `store_finding()` to handle version snapshot persistence cleanly without violating primary key or foreign key constraints.

---

## 4. Implementation Details

- Queries filter by `logical_id` and select the max `version` (parsed from row or `versions_json`).
- If no existing record matches `logical_id`, returns `None`.

---

## 5. Public API Changes

- `Database.get_latest_finding_by_logical_id(logical_id: str) -> Optional[Finding]` added to public `Database` storage interface.

---

## 6. Backward Compatibility Requirements

- Guaranteed compatibility with legacy database rows where `logical_id` is `NULL`.
- Queries for non-existent `logical_id` safely return `None`.

---

## 7. Rollback Strategy

- Remove `get_latest_finding_by_logical_id()` method from `src/mtklab/storage/db.py`.
- Revert changes to `store_finding()`.
- Remove tests from `tests/test_storage.py`.

---

## 8. Edge Cases & Validation

- `logical_id` not found in database: Returns `None`.
- Multiple finding rows matching `logical_id`: Correctly orders by highest version and returns latest snapshot.
- Unparseable `versions_json` or empty versions array: Gracefully defaults version count to 1.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Test `get_latest_finding_by_logical_id()` with no matching records.
  - Test `get_latest_finding_by_logical_id()` with multiple existing versions, ensuring highest version is returned.
- **Integration Tests**:
  - Store sequential finding versions in `Database` and verify lookup retrieves latest version.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `get_latest_finding_by_logical_id()` implemented in `Database`.
- [ ] Correctly retrieves highest version snapshot for a given `logical_id`.
- [ ] Storage tests pass (`pytest tests/test_storage.py`).

---

## 11. Code Review Checklist

- [ ] SQL query correctly handles parameter binding to avoid SQL injection.
- [ ] Row mapping correctly reconstructs `Finding` object with all versions.
- [ ] Comprehensive unit tests for single, multiple, and missing finding lookups.

---

## 12. Related Documents

- [Domain API Specification](../architecture/DOMAIN_API.md)
- [ADR-003: Logical ID Deduplication](../architecture/ADR/ADR-003-logical-id-deduplication.md)
- [MTKLAB-002 Specification](./MTKLAB-002.md)
