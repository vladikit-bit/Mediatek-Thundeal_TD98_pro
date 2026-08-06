# Developer Specification: MTKLAB-004

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Logical ID Deduplication Workflow](#4-logical-id-deduplication-workflow)
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
Wire `logical_id` deduplication and versioning workflow into `EvidenceEngine.submit_finding()`, ensuring new findings start at version 1, modified findings increment version, and unchanged findings avoid duplicate versions.

---

## 2. Files to Modify
1. `src/mtklab/core/evidence.py`
2. `tests/test_evidence_engine.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/core/evidence.py`
Update `EvidenceEngine.submit_finding()`:
```python
def submit_finding(self, finding: Finding, evidences: Optional[List[Evidence]] = None) -> Finding:
    if not finding.logical_id:
        finding.logical_id = generate_logical_id(
            finding.experiment_id, finding.kind, finding.offset, finding.size
        )
        
    existing = self.db.get_latest_finding_by_logical_id(finding.logical_id)
    if existing:
        if self._is_finding_unchanged(existing, finding):
            return existing
        latest_ver = self._get_latest_version_num(existing)
        new_ver_num = latest_ver + 1
        finding.finding_id = str(uuid.uuid4())
        finding.add_version(
            confidence=finding.confidence,
            label=finding.label,
            description=finding.description,
            evidence_ids=finding.evidence_ids,
            metadata=finding.metadata,
            reason="updated"
        )
    else:
        if not finding.versions:
            finding.add_version(
                confidence=finding.confidence,
                label=finding.label,
                description=finding.description,
                evidence_ids=finding.evidence_ids,
                metadata=finding.metadata,
                reason="created"
            )
            
    self.db.store_finding(finding)
    return finding
```

---

## 4. Logical ID Deduplication Workflow

- **Lookup**: Engine queries `get_latest_finding_by_logical_id()`.
- **Comparison**: If existing finding matches label, description, confidence, and metadata, execution returns existing finding without creating a new DB record.
- **Increment**: If content differs, `version` is incremented ($N+1$) and stored as a new `finding_id` snapshot.

---

## 5. Public API Changes

- `EvidenceEngine.submit_finding(finding, evidences)` signature preserved; behavior updated to handle `logical_id` versioning transparently.

---

## 6. Backward Compatibility Requirements

- Legacy finding submission behavior without pre-existing `logical_id` auto-generates canonical `logical_id`.
- Fully backward-compatible with existing experiments.

---

## 7. Rollback Strategy

- Revert changes to `EvidenceEngine.submit_finding()`.
- Remove `_is_finding_unchanged()` and `_get_latest_version_num()` helper functions.
- Revert tests in `tests/test_evidence_engine.py`.

---

## 8. Edge Cases & Validation

- Unchanged finding resubmitted multiple times: Returns existing `Finding` instance without adding records to DB.
- Finding updated with new confidence or metadata: Generates new UUID `finding_id` with incremented `version` number.
- Missing `versions` list on new finding: Automatically populates version 1 with `reason="created"`.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Submitting a new finding creates Version 1.
  - Submitting identical finding again returns Version 1 without creating duplicate DB entry.
  - Submitting modified finding creates Version 2 with new UUID `finding_id`.
- **Integration Tests**:
  - Run multi-step experiment simulation and verify version evolution history.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `submit_finding()` deduplicates identical findings by `logical_id`.
- [ ] Modified findings auto-increment version number ($N+1$).
- [ ] All engine tests pass (`pytest tests/test_evidence_engine.py`).

---

## 11. Code Review Checklist

- [ ] Unchanged detection covers label, description, confidence, and metadata equality.
- [ ] Version numbers increment strictly monotonically ($1, 2, 3$).
- [ ] Tests verify new, duplicate, and modified finding workflows.

---

## 12. Related Documents

- [Domain API Specification](../architecture/DOMAIN_API.md#4-finding-lifecycle--submit_finding-flow)
- [ADR-003: Logical ID Deduplication](../architecture/ADR/ADR-003-logical-id-deduplication.md)
- [MTKLAB-003 Specification](./MTKLAB-003.md)
