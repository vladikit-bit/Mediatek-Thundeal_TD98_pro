# Developer Specification: MTKLAB-005

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Content Hash Formula](#4-content-hash-formula)
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
Implement content-addressed SHA-256 evidence hashing in `Evidence` dataclass to ensure deterministic, reproducible `evidence_id` generation based on payload content.

---

## 2. Files to Modify
1. `src/mtklab/core/evidence.py`
2. `tests/test_evidence.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/core/evidence.py`
Add method `compute_content_hash()` to `Evidence`:
```python
def compute_content_hash(self) -> str:
    """Compute deterministic SHA-256 hash of evidence payload."""
    data_str = json.dumps(self.data, sort_keys=True)
    canonical = f"{self.experiment_id}:{self.evidence_type}:{self.source_offset}:{self.source_size}:{data_str}"
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

Update `Evidence.__post_init__()` to populate `evidence_id` with `compute_content_hash()` if `evidence_id` is not explicitly provided.

---

## 4. Content Hash Formula

- Payload ingredients: `experiment_id`, `evidence_type`, `source_offset`, `source_size`, `json.dumps(data, sort_keys=True)`.
- Hash algorithm: SHA-256.
- Output: 64-character lowercase hex string.

---

## 5. Public API Changes

- `Evidence.compute_content_hash() -> str` added to `Evidence` class.
- `evidence_id` default computation transitions from random UUID to SHA-256 content hash.

---

## 6. Backward Compatibility Requirements

- If explicit `evidence_id` string is provided during instantiation, it is preserved.
- Legacy records using UUID string format remain valid when read from database.

---

## 7. Rollback Strategy

- Revert `compute_content_hash()` implementation.
- Restore `uuid.uuid4()` default generation in `Evidence.__post_init__()`.
- Revert unit tests in `tests/test_evidence.py`.

---

## 8. Edge Cases & Validation

- `data` dictionary keys out of order: `json.dumps(..., sort_keys=True)` guarantees identical hash regardless of dict key insertion order.
- `source_offset` or `source_size` is `None`: Converted to string `"None"` in canonical formatting.
- Binary or non-string values in `data`: Handled via custom JSON encoder or serialized appropriately.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Test verifying identical evidence payloads produce identical SHA-256 hashes.
  - Test verifying modified evidence fields produce distinct SHA-256 hashes.
  - Test verifying dict key order does not alter the generated hash.
- **Integration Tests**:
  - Instantiate multiple evidence objects across runs and verify hash collision behavior.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `compute_content_hash()` implemented and tested.
- [ ] `Evidence` automatically uses content-addressed `evidence_id` when omitted.
- [ ] All unit tests pass (`pytest tests/test_evidence.py`).

---

## 11. Code Review Checklist

- [ ] `json.dumps` uses `sort_keys=True` for determinism.
- [ ] Hash string is 64-character hex digest (`.hexdigest()`).
- [ ] Tests verify hash stability across python process restarts.

---

## 12. Related Documents

- [RFC Document](../architecture/RFC.md#31-identity-management)
- [ADR-002: Content-Addressed Evidence](../architecture/ADR/ADR-002-content-addressed-evidence.md)
- [MTKLAB-004 Specification](./MTKLAB-004.md)
