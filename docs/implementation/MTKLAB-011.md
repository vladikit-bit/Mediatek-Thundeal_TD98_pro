# Developer Specification: MTKLAB-011

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Formatting & Output Enhancements](#4-formatting--output-enhancements)
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
Update CLI `status` and `inspect` commands to render versioned finding histories, `logical_id` summaries, content-addressed evidence hashes, and historical execution run summaries.

---

## 2. Files to Modify
1. `src/mtklab/cli.py`
2. `tests/test_cli.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/cli.py`
- Update `mtklab status`:
  - Display summary of total runs, total findings, and unique `logical_id` count.
  - Show breakdown of findings by confidence (`CANDIDATE`, `PROBABLE`, `VERIFIED`).
- Update `mtklab inspect <logical_id_or_id>`:
  - Display full version timeline for matching `logical_id`.
  - Show associated content-addressed `evidence_id` hashes and evidence details.

---

## 4. Formatting & Output Enhancements

- Standardized tabular output using Rich or standard terminal formatting.
- Clear distinction between logical findings and version snapshots.

---

## 5. Public API Changes

- `mtklab status` output includes run count, logical findings count, and version summaries.
- `mtklab inspect` accepts `logical_id` or `finding_id` and prints formatted version timeline.

---

## 6. Backward Compatibility Requirements

- `mtklab inspect` remains compatible with legacy UUID `finding_id` lookups as well as new `logical_id` string lookups.

---

## 7. Rollback Strategy

- Revert changes to `status` and `inspect` command functions in `src/mtklab/cli.py`.
- Revert CLI tests in `tests/test_cli.py`.

---

## 8. Edge Cases & Validation

- `mtklab inspect` called with non-existent `logical_id`: Displays clear warning message ("No finding found for logical_id: ...") and exits with status 1.
- Project database has zero runs or zero findings: Displays empty state summary without raising tracebacks.

---

## 9. Testing Requirements

- **Unit Tests**:
  - Test `mtklab status` output rendering on sample project database.
  - Test `mtklab inspect` retrieving version history and evidence links for a given `logical_id`.
- **Integration Tests**:
  - Run full CLI lifecycle (`run`, `status`, `inspect`) via subprocess or Click runner and verify CLI exit codes and output formatting.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] `mtklab status` displays runs, logical findings, and confidence breakdown.
- [ ] `mtklab inspect` displays complete finding version history.
- [ ] All CLI tests pass (`pytest tests/test_cli.py`).

---

## 11. Code Review Checklist

- [ ] Terminal formatting clean and readable on standard terminals.
- [ ] Handles missing or invalid `logical_id` with helpful error message.
- [ ] Tests assert expected CLI output strings and return codes.

---

## 12. Related Documents

- [Domain API Specification](../architecture/DOMAIN_API.md)
- [Issue Backlog](../architecture/ISSUE_BACKLOG.md#mtklab-011-update-cli-status-and-inspect-for-versions--runs)
- [MTKLAB-010 Specification](./MTKLAB-010.md)
