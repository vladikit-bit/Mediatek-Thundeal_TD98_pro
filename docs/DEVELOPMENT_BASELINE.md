# MTKLab Development Baseline

## Table of Contents
- [1. Baseline Declaration](#1-baseline-declaration)
- [2. Baseline Metadata & Document Versions](#2-baseline-metadata--document-versions)
- [3. Approved ADR List](#3-approved-adr-list)
- [4. Implementation Order](#4-implementation-order)
- [5. Coding Rules](#5-coding-rules)
- [6. Review Rules & Governance](#6-review-rules--governance)
- [7. Change Management Statement](#7-change-management-statement)
- [8. Related Documents](#8-related-documents)

---

## 1. Baseline Declaration

This document formally declares the complete, approved engineering documentation set as the official **Implementation Baseline** for MTKLab. All subsequent software engineering, pull requests, and codebase modifications MUST strictly align with the decisions, specifications, and workflows established in this baseline.

---

## 2. Baseline Metadata & Document Versions

| Entity / Artifact | Version | Canonical Path | Description |
| :--- | :--- | :--- | :--- |
| **Architecture Version** | `v1.0` | [`docs/architecture/RFC.md`](./architecture/RFC.md) | High-Level Architecture & Domain Model |
| **Implementation Package** | `v1.0` | [`docs/implementation/`](./implementation/) | Developer Specifications MTKLAB-001–011 |
| **Domain API Specification** | `v1.0` | [`docs/architecture/DOMAIN_API.md`](./architecture/DOMAIN_API.md) | Component Boundaries & Engine Contracts |
| **Implementation Roadmap** | `v1.0` | [`docs/architecture/ROADMAP.md`](./architecture/ROADMAP.md) | Phased Delivery Strategy (v1.1 – v2.0) |
| **Issue Backlog** | `v1.0` | [`docs/architecture/ISSUE_BACKLOG.md`](./architecture/ISSUE_BACKLOG.md) | Backlog Matrix & PR Definitions |
| **PR Quality Checklist** | `v1.0` | [`docs/development/PR_CHECKLIST.md`](./development/PR_CHECKLIST.md) | Developer Pre-Submission Criteria |
| **Review Guidelines** | `v1.0` | [`docs/development/REVIEW_GUIDELINES.md`](./development/REVIEW_GUIDELINES.md) | Maintainer Review Standards |

---

## 3. Approved ADR List

1. **[ADR-001: Execution Run Tracking Model](./architecture/ADR/ADR-001-runs-and-executions.md)** (`v1.0`)
   - Introduces `runs` and `experiment_runs` SQLite tables to track session execution provenance and configuration history.
2. **[ADR-002: Content-Addressed Evidence Identification](./architecture/ADR/ADR-002-content-addressed-evidence.md)** (`v1.0`)
   - Replaces random UUIDs with SHA-256 content hashes (`evidence_id`) derived from normalized payload fields.
3. **[ADR-003: Logical ID Deduplication and Finding Versioning](./architecture/ADR/ADR-003-logical-id-deduplication.md)** (`v1.0`)
   - Decouples stable semantic finding identity (`logical_id`) from version snapshot identities (`finding_id` UUIDs).
4. **[ADR-004: SQLite Schema Evolution Strategy](./architecture/ADR/ADR-004-sqlite-schema-evolution.md)** (`v1.0`)
   - Defines migration tracking via `schema_migrations` table and sequential `0XX_*.sql` migration scripts.

---

## 4. Implementation Order

Implementation MUST proceed strictly in the following sequential order. Each issue corresponds to a single, independently testable pull request:

| Step | Issue Key | Complexity | Target Module / Scope | Status | Specification Reference |
| :---: | :--- | :---: | :--- | :---: | :--- |
| **1** | **MTKLAB-001** | **S** | Migration `002_logical_ids.sql`, `Finding` dataclass & `db.py` fixes | **MERGED** | [`MTKLAB-001.md`](./implementation/MTKLAB-001.md) |
| **2** | **MTKLAB-002** | **XS** | Canonical `generate_logical_id()` helper generator | Pending | [`MTKLAB-002.md`](./implementation/MTKLAB-002.md) |
| **3** | **MTKLAB-003** | **M** | `Database.get_latest_finding_by_logical_id()` lookup | Pending | [`MTKLAB-003.md`](./implementation/MTKLAB-003.md) |
| **4** | **MTKLAB-004** | **M** | `EvidenceEngine.submit_finding()` `logical_id` deduplication | Pending | [`MTKLAB-004.md`](./implementation/MTKLAB-004.md) |
| **5** | **MTKLAB-005** | **S** | SHA-256 `compute_content_hash()` in `Evidence` | Pending | [`MTKLAB-005.md`](./implementation/MTKLAB-005.md) |
| **6** | **MTKLAB-006** | **S** | Storage layer evidence deduplication (`INSERT OR IGNORE`) | Pending | [`MTKLAB-006.md`](./implementation/MTKLAB-006.md) |
| **7** | **MTKLAB-007** | **M** | Migration `003_junctions.sql` (`finding_evidences`, `hypothesis_evidences`) | Pending | [`MTKLAB-007.md`](./implementation/MTKLAB-007.md) |
| **8** | **MTKLAB-008** | **M** | Engine & storage refactoring for junction table JOIN queries | Pending | [`MTKLAB-008.md`](./implementation/MTKLAB-008.md) |
| **9** | **MTKLAB-009** | **S** | Migration `004_runs.sql` (`runs` & `experiment_runs`) | Pending | [`MTKLAB-009.md`](./implementation/MTKLAB-009.md) |
| **10** | **MTKLAB-010** | **M** | Execution run tracking context in `ExperimentContext` and CLI | Pending | [`MTKLAB-010.md`](./implementation/MTKLAB-010.md) |
| **11** | **MTKLAB-011** | **M** | CLI `status` and `inspect` command updates for runs & versions | Pending | [`MTKLAB-011.md`](./implementation/MTKLAB-011.md) |

---

## 5. Coding Rules

All code written during implementation MUST adhere to these mandatory rules:

1. **Python Standards**: Python 3.10+ clean, type-annotated code with standard docstrings for public classes and methods.
2. **No Unapproved Abstractions**: Do NOT introduce new design patterns, speculative interfaces, or additional database tables outside approved specifications.
3. **Database & Schema Rules**:
   - Enable foreign keys (`PRAGMA foreign_keys = ON`).
   - Use `INSERT OR IGNORE` instead of `INSERT OR REPLACE` when saving deduplicated records to prevent accidental cascading deletes.
   - All migrations must be idempotent (`IF NOT EXISTS`).
4. **Backward Compatibility**:
   - Preserve default parameters for legacy object deserialization (`to_dict()`, `from_dict()`).
   - Support seamless upgrade paths for existing SQLite databases (`data/projects/<id>/evidence.db`).
5. **Testing Minimums**:
   - Every modified module MUST have accompanying unit tests.
   - SQLite migrations MUST have automated initialization tests.

---

## 6. Review Rules & Governance

Maintainers and developers MUST enforce the following review standards:

1. **PR Checklist**: Submissions MUST satisfy all criteria in [`PR_CHECKLIST.md`](./development/PR_CHECKLIST.md).
2. **Review Categories**:
   - `[BLOCKER]`: Architectural deviation, breaking API change, or migration failure. Halts merge.
   - `[RECOMMENDED]`: Maintainability or performance refinement.
   - `[NITPICK]`: Minor style recommendation.
3. **Definition of Done**:
   - Scope limited to a single issue (one PR).
   - All automated tests (`pytest`) pass green.
   - All blockers resolved and approved by at least one maintainer.

---

## 7. Change Management Statement

> **CRITICAL DIRECTIVE**: Implementation MUST strictly follow the baseline documentation set. **No architectural changes, scope additions, or API redesigns are permitted** during implementation without first updating and obtaining formal approval for the corresponding RFC, Domain API, or ADR document.

---

## 8. Related Documents

- [Architecture RFC](./architecture/RFC.md)
- [Domain API Specification](./architecture/DOMAIN_API.md)
- [Implementation Roadmap](./architecture/ROADMAP.md)
- [Issue Backlog](./architecture/ISSUE_BACKLOG.md)
- [PR Quality Checklist](./development/PR_CHECKLIST.md)
- [Code Review Guidelines](./development/REVIEW_GUIDELINES.md)
