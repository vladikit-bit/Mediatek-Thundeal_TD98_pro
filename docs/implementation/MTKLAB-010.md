# Developer Specification: MTKLAB-010

## Table of Contents
- [1. Objective](#1-objective)
- [2. Files to Modify](#2-files-to-modify)
- [3. Code Locations & Changes](#3-code-locations--changes)
- [4. Execution Flow Integration](#4-execution-flow-integration)
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
Integrate execution run context into `ExperimentContext`, `EvidenceEngine`, and CLI commands, automatically recording session `run_id` and experiment outcomes during execution.

---

## 2. Files to Modify
1. `src/mtklab/core/context.py`
2. `src/mtklab/cli.py`
3. `src/mtklab/storage/db.py`
4. `tests/test_cli.py`

---

## 3. Code Locations & Changes

### 3.1 `src/mtklab/core/context.py`
- Add `run_id: Optional[str] = None` property to `ExperimentContext`.

### 3.2 `src/mtklab/cli.py`
- Update `mtklab run` command handler to generate a new `run_id` (UUID), create a record in `runs` table, and pass `run_id` into context when executing experiments.
- Record duration, status, and error messages in `experiment_runs` table upon experiment completion or failure.

---

## 4. Execution Flow Integration

1. `mtklab run` generates `run_id = str(uuid.uuid4())`.
2. Inserts parent record into `runs`.
3. Passes `run_id` to `ExperimentContext`.
4. Wraps experiment execution in timer and try/except block to insert `experiment_runs` records.

---

## 5. Public API Changes

- `ExperimentContext` initialized with optional `run_id: Optional[str] = None`.
- CLI execution automatically records run tracking metadata in SQLite storage.

---

## 6. Backward Compatibility Requirements

- Executing experiments outside CLI context (e.g., in unit tests without `run_id`) defaults `run_id` to `None` without raising errors.

---

## 7. Rollback Strategy

- Revert `run_id` additions in `ExperimentContext`.
- Remove run tracking recording logic from `mtklab run` command handler in `src/mtklab/cli.py`.
- Revert CLI tests in `tests/test_cli.py`.

---

## 8. Edge Cases & Validation

- Experiment raises uncaught exception during execution: Trapped, status recorded as `FAILED`, exception trace stored in `error_message`, and exception re-raised or handled gracefully.
- User cancels run via SIGINT (Ctrl+C): Status captured as `CANCELLED` if possible.

---

## 9. Testing Requirements

- **Unit Tests**:
  - `ExperimentContext` correctly holds `run_id`.
  - Storage methods insert run and experiment run records.
- **Integration Tests**:
  - Unit test running an experiment via CLI populates `runs` and `experiment_runs` DB tables.
  - Test error handling records `status='FAILED'` and captures exception traceback in `error_message`.

---

## 10. Acceptance Criteria & Definition of Done

- [ ] CLI `run` creates parent run and experiment run records in DB.
- [ ] Experiment status and execution timing accurately recorded.
- [ ] Integration CLI tests pass (`pytest tests/test_cli.py`).

---

## 11. Code Review Checklist

- [ ] `run_id` correctly propagated through `ExperimentContext`.
- [ ] Try/finally block ensures duration and status recorded even on exception.
- [ ] Tests verify failed experiment run recording.

---

## 12. Related Documents

- [ADR-001: Execution Run Tracking Model](../architecture/ADR/ADR-001-runs-and-executions.md)
- [MTKLAB-009 Specification](./MTKLAB-009.md)
