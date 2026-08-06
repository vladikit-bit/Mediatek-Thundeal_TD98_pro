# ADR-001: Execution Run Tracking Model

## Table of Contents
- [1. Context](#1-context)
- [2. Decision](#2-decision)
- [3. Consequences](#3-consequences)
- [4. Related Documents](#4-related-documents)

---

## 1. Context
Previously, experiment outputs were associated directly with a project, making it impossible to distinguish between distinct execution sessions, historical reruns, or configuration changes over time.

---

## 2. Decision
We introduce explicit `runs` and `experiment_runs` tables:
- `runs`: Captures CLI invocation metadata (`run_id`, `project_id`, `created_at`, `command`, `config_json`).
- `experiment_runs`: Tracks specific experiment executions within a parent run (`experiment_run_id`, `run_id`, `experiment_id`, `status`, `duration_seconds`).

---

## 3. Consequences
### Positive
- Complete provenance tracking for every finding and evidence record.
- Ability to audit run parameters and compare historical experiment outputs.

### Negative
- Requires passing `run_id` through `ExperimentContext` and `EvidenceEngine`.
- Additional database queries during execution setup.

---

## 4. Related Documents
- [RFC Document](../RFC.md)
- [Roadmap](../ROADMAP.md)
- [MTKLAB-009 Specification](../../implementation/MTKLAB-009.md)
- [MTKLAB-010 Specification](../../implementation/MTKLAB-010.md)
