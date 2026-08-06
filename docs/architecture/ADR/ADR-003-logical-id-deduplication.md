# ADR-003: Logical ID Deduplication and Finding Versioning

## Table of Contents
- [1. Context](#1-context)
- [2. Decision](#2-decision)
- [3. Consequences](#3-consequences)
- [4. Related Documents](#4-related-documents)

---

## 1. Context
Findings were identified solely by a primary UUID, resulting in duplicate entries on re-running experiments and preventing incremental tracking of binary discovery evolution.

---

## 2. Decision
We separate logical identity from version snapshot identity:
- `logical_id`: Human-readable, stable identity string (`<experiment_id>:<kind>:<offsets>`).
- `finding_id`: UUIDv4 identifying a specific version snapshot of a finding.
- Versioning behavior: When an experiment submits a finding with an existing `logical_id`, the engine compares properties. If modified, `version` is incremented and a new `finding_id` snapshot is stored. If unchanged, duplicate version creation is skipped.

---

## 3. Consequences
### Positive
- Clear audit history of how findings evolve from `CANDIDATE` to `VERIFIED`.
- Eliminates duplicate finding rows across repeated CLI runs.

### Negative
- Queries for the "latest" finding state must group by or filter on `logical_id` and maximum `version`.

---

## 4. Related Documents
- [RFC Document](../RFC.md)
- [Domain API Specification](../DOMAIN_API.md)
- [MTKLAB-001 Specification](../../implementation/MTKLAB-001.md)
- [MTKLAB-003 Specification](../../implementation/MTKLAB-003.md)
- [MTKLAB-004 Specification](../../implementation/MTKLAB-004.md)
