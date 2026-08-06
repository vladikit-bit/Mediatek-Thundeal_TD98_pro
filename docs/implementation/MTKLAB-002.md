# Developer Specification: MTKLAB-002

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Formatting Rules & Invariants](#4-formatting-rules--invariants)
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
Implement a standard canonical helper function `generate_logical_id()` in `src/mtklab/core/evidence.py` to generate deterministic `logical_id` strings for `Finding` objects based on experiment ID, finding kind, and binary offsets.

---

## 2. Files to Modify
1. `src/mtklab/core/evidence.py`
2. `tests/test_evidence.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/core/evidence.py`
Add top-level helper function:
```python
def generate_logical_id(experiment_id: str, kind: str, offset: Optional[int], size: Optional[int]) -> str:
    """Generate a canonical logical_id for a finding."""
    if offset is None or size is None:
        return f"{experiment_id}:{kind}:global"
    end_offset = offset + size
    return f"{experiment_id}:{kind}:0x{offset:08x}-0x{end_offset:08x}"
```

Update `Finding.__post_init__()` or instantiation logic to auto-populate `logical_id` using `generate_logical_id` if `logical_id` is not explicitly supplied.

---

## 4. Formatting Rules & Invariants

- Offset hex addresses are zero-padded to 8 hexadecimal digits (`0x00000000`).
- If `offset` or `size` is `None`, falls back to `:global`.
- Lowercase string output.

---

## 5. Public API Changes

- Expose `generate_logical_id(experiment_id: str, kind: str, offset: Optional[int], size: Optional[int]) -> str` in `src/mtklab/core/evidence.py`.

---

## 6. Backward Compatibility Requirements

- Non-breaking addition: Existing findings or experiments that pass a custom `logical_id` retain their custom value.
- If `logical_id` is missing, default generation produces canonical format without error.

---

## 7. Rollback Strategy

- Revert `generate_logical_id()` helper function from `src/mtklab/core/evidence.py`.
- Revert auto-generation in `Finding.__post_init__()`.
- Remove corresponding tests from `tests/test_evidence.py`.

---

## 8. Edge Cases & Validation

- `offset` set, `size` is `None`: Falls back to `:global`.
- `offset` is `None`, `size` set: Falls back to `:global`.
- Large offset values (e.g. > 32-bit): Handled cleanly by string formatting (`0x...`).
- Special characters in `experiment_id` or `kind`: Output formatted as clean ASCII.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Test `generate_logical_id` with valid offset and size (e.g., `offset=0`, `size=0x8000`).
  - Test `generate_logical_id` with `None` offset or size.
  - Verify zero-padding format (`0x00000000-0x00008000`).
- **Integration Tests**:
  - Verify `Finding` instantiation populates `logical_id` automatically when omitted.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `generate_logical_id()` helper function implemented and exported in `src/mtklab/core/evidence.py`.
- [ ] Returns expected string format for regional and global findings.
- [ ] `Finding` dataclass auto-generates `logical_id` if none provided.
- [ ] All unit and integration tests pass (`pytest tests/test_evidence.py`).

---

## 11. Code Review Checklist

- [ ] Conforms to canonical string format `<exp_id>:<kind>:<offsets>`.
- [ ] Proper type annotations (`Optional[int]`, `str`).
- [ ] Unit tests cover all branches (`offset/size` present vs `None`).

---

## 12. Related Documents

- [Domain API Specification](../architecture/DOMAIN_API.md#3-logical-id-generation--ownership)
- [ADR-003: Logical ID Deduplication](../architecture/ADR/ADR-003-logical-id-deduplication.md)
- [MTKLAB-001 Specification](./MTKLAB-001.md)
