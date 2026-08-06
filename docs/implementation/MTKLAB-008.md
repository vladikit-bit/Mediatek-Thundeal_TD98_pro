# Developer Specification: MTKLAB-008

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
Refactor `EvidenceEngine` and `Database` layer to populate and query the normalized `finding_evidences` and `hypothesis_evidences` junction tables during finding and hypothesis submission.

---

## 2. Files to Modify
1. `src/mtklab/core/evidence.py`
2. `src/mtklab/storage/db.py`
3. `tests/test_evidence_engine.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/storage/db.py`
- Add method `link_finding_evidences(finding_id: str, evidence_ids: List[str])`:
  ```python
  def link_finding_evidences(self, finding_id: str, evidence_ids: List[str]):
      for eid in evidence_ids:
          self._conn.execute(
              "INSERT OR IGNORE INTO finding_evidences (finding_id, evidence_id) VALUES (?, ?)",
              (finding_id, eid)
          )
  ```
- Update `get_evidences_for_finding(finding_id: str) -> List[Evidence]` to JOIN `finding_evidences`.

### 3.2 `src/mtklab/core/evidence.py`
- Update `submit_finding()` to invoke `link_finding_evidences()`.

---

## 4. Implementation Details

- Integrates normalized database queries while maintaining backward-compatible `evidence_ids` array properties on domain models.

---

## 5. Public API Changes

- `Database.link_finding_evidences(finding_id: str, evidence_ids: List[str]) -> None` added to database interface.
- `Database.get_evidences_for_finding(finding_id: str) -> List[Evidence]` refactored to use SQL JOIN on junction table.

---

## 6. Backward Compatibility Requirements

- Domain model `finding.evidence_ids` continues to return array of strings.
- Deprecated JSON column array remains populated for fallback compatibility during transition.

---

## 7. Rollback Strategy

- Revert changes to `Database.get_evidences_for_finding()` and `EvidenceEngine.submit_finding()`.
- Remove `Database.link_finding_evidences()` method.
- Revert test files.

---

## 8. Edge Cases & Validation

- `evidence_ids` list is empty: Safely no-ops without database error.
- Non-existent `evidence_id` referenced: Handled gracefully or caught by DB constraint.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Unit test verifying submitting a finding inserts links into `finding_evidences`.
  - Unit test verifying `get_evidences_for_finding()` fetches linked evidence correctly via SQL JOIN.
- **Integration Tests**:
  - Submit finding with multiple evidence items and query back full populated entities.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `finding_evidences` links populated on finding submission.
- [ ] Evidence records retrievable via normalized JOIN query.
- [ ] Integration tests pass (`pytest tests/test_evidence_engine.py`).

---

## 11. Code Review Checklist

- [ ] `INSERT OR IGNORE` used for junction records.
- [ ] SQL JOIN query correctly projects evidence columns.
- [ ] Tests verify junction table population and retrieval.

---

## 12. Related Documents

- [Domain API Specification](../architecture/DOMAIN_API.md#4-finding-lifecycle--submit_finding-flow)
- [MTKLAB-007 Specification](./MTKLAB-007.md)
