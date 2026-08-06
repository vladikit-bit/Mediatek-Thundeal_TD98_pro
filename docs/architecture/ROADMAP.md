# MTKLab Implementation Roadmap

## Table of Contents
- [1. Executive Overview](#1-executive-overview)
- [2. Phase Breakdown](#2-phase-breakdown)
- [3. Phase Dependency Graph](#3-phase-dependency-graph)
- [4. Release Milestones](#4-release-milestones)
- [5. Related Documents](#5-related-documents)

---

## 1. Executive Overview

This document outlines the phased implementation roadmap for upgrading MTKLab's storage model, deduplication engine, and finding versioning architecture. The migration strategy prioritizes backward compatibility, zero downtime for existing projects, and small, testable increments.

---

## 2. Phase Breakdown

### Phase 1: Database Foundation & Schema Migration (v1.1)
- **Goal**: Fix SQLite constraint handling and add the `logical_id` column to findings.
- **Key Changes**:
  - Add `002_logical_ids.sql` schema migration.
  - Fix `INSERT OR REPLACE` anti-pattern in `Database` storage layer.
  - Update `Finding` dataclass to support `logical_id`.
- **Target Issues**: [MTKLAB-001](../implementation/MTKLAB-001.md)

### Phase 2: Engine Deduplication & Versioning Logic (v1.1)
- **Goal**: Implement deterministic `logical_id` generation and version incrementing in `EvidenceEngine`.
- **Key Changes**:
  - Implement `generate_logical_id()` helper.
  - Add finding lookup and version increment logic during submission.
- **Target Issues**: [MTKLAB-002](../implementation/MTKLAB-002.md), [MTKLAB-003](../implementation/MTKLAB-003.md), [MTKLAB-004](../implementation/MTKLAB-004.md)

### Phase 3: Content-Addressed Evidence Engine (v1.2)
- **Goal**: Transition Evidence identifiers from random UUIDs to SHA-256 content-addressed hashes.
- **Key Changes**:
  - Add deterministic SHA-256 hash generation for Evidence.
  - Implement storage deduplication for evidence records.
- **Target Issues**: [MTKLAB-005](../implementation/MTKLAB-005.md), [MTKLAB-006](../implementation/MTKLAB-006.md)

### Phase 4: Normalized Junction Linkages (v1.2)
- **Goal**: Replace JSON array evidence links with normalized junction tables (`finding_evidences`, `hypothesis_evidences`).
- **Key Changes**:
  - Add `003_junctions.sql` migration.
  - Refactor `EvidenceEngine` and `Database` queries to utilize junction tables.
- **Target Issues**: [MTKLAB-007](../implementation/MTKLAB-007.md), [MTKLAB-008](../implementation/MTKLAB-008.md)

### Phase 5: Run Execution Management & CLI Enhancement (v2.0)
- **Goal**: Introduce explicit `runs` and `experiment_runs` tables to track session history.
- **Key Changes**:
  - Add `004_runs.sql` migration.
  - Integrate Run context into CLI commands (`run`, `status`, `inspect`).
- **Target Issues**: [MTKLAB-009](../implementation/MTKLAB-009.md), [MTKLAB-010](../implementation/MTKLAB-010.md), [MTKLAB-011](../implementation/MTKLAB-011.md)

---

## 3. Phase Dependency Graph

```text
+---------------------------------------+
| Phase 1: Schema & Logical ID Column   |
+---------------------------------------+
                    |
                    v
+---------------------------------------+
| Phase 2: Deduplication & Versioning   |
+---------------------------------------+
                    |
                    v
+---------------------------------------+
| Phase 3: Content-Addressed Evidence   |
+---------------------------------------+
                    |
                    v
+---------------------------------------+
| Phase 4: Normalized Junction Tables   |
+---------------------------------------+
                    |
                    v
+---------------------------------------+
| Phase 5: Run Tracking & CLI Tooling   |
+---------------------------------------+
```

---

## 4. Release Milestones

| Milestone | Target Phase | Description | Key Deliverable |
| :--- | :--- | :--- | :--- |
| **v1.1** | Phases 1 & 2 | Logical ID support & versioned findings | `002_logical_ids.sql` + `logical_id` deduplication |
| **v1.2** | Phases 3 & 4 | Content-addressed evidence & junction tables | `003_junctions.sql` + SHA-256 evidence hashing |
| **v2.0** | Phase 5 | Execution Run tracking & CLI inspection | `004_runs.sql` + session run management |

---

## 5. Related Documents

- [RFC Document](./RFC.md)
- [Domain API Specification](./DOMAIN_API.md)
- [Issue Backlog](./ISSUE_BACKLOG.md)
- Architecture Decision Records:
  - [ADR-001: Runs & Executions](./ADR/ADR-001-runs-and-executions.md)
  - [ADR-002: Content-Addressed Evidence](./ADR/ADR-002-content-addressed-evidence.md)
  - [ADR-003: Logical ID Deduplication](./ADR/ADR-003-logical-id-deduplication.md)
  - [ADR-004: SQLite Schema Evolution](./ADR/ADR-004-sqlite-schema-evolution.md)
