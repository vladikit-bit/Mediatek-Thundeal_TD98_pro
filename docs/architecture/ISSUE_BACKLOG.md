# MTKLab Engineering Issue Backlog

## Table of Contents
- [1. Backlog Overview](#1-backlog-overview)
- [2. Issue Summary Matrix](#2-issue-summary-matrix)
- [3. Detailed Issue Specifications](#3-detailed-issue-specifications)
- [4. Related Documents](#4-related-documents)

---

## 1. Backlog Overview

This document presents the complete engineering backlog for executing the MTKLab architecture upgrade. Each task represents a single pull request with explicit boundaries, test coverage requirements, and acceptance criteria.

---

## 2. Issue Summary Matrix

| Issue Key | Title | Complexity | PR Scope | Dependencies | Implementation Spec |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MTKLAB-001** | Add `002_logical_ids.sql` Migration & Storage Fixes | **S** | DB Schema / Storage | None | [MTKLAB-001.md](../implementation/MTKLAB-001.md) |
| **MTKLAB-002** | Add Canonical `logical_id` Helper Generator | **XS** | Core Domain | MTKLAB-001 | [MTKLAB-002.md](../implementation/MTKLAB-002.md) |
| **MTKLAB-003** | Implement Finding Lookup and Upsert in Database | **M** | Storage Layer | MTKLAB-001, MTKLAB-002 | [MTKLAB-003.md](../implementation/MTKLAB-003.md) |
| **MTKLAB-004** | Wire `logical_id` Deduplication in `EvidenceEngine` | **M** | Core Engine | MTKLAB-003 | [MTKLAB-004.md](../implementation/MTKLAB-004.md) |
| **MTKLAB-005** | Implement Content-Addressed SHA-256 Evidence Hashing | **S** | Core Evidence | MTKLAB-004 | [MTKLAB-005.md](../implementation/MTKLAB-005.md) |
| **MTKLAB-006** | Implement Evidence Deduplication in Storage Layer | **S** | Storage Layer | MTKLAB-005 | [MTKLAB-006.md](../implementation/MTKLAB-006.md) |
| **MTKLAB-007** | Add `003_junctions.sql` Migration for Linkage Tables | **M** | DB Schema | MTKLAB-006 | [MTKLAB-007.md](../implementation/MTKLAB-007.md) |
| **MTKLAB-008** | Refactor Engine and Storage for Junction Tables | **M** | Core / Storage | MTKLAB-007 | [MTKLAB-008.md](../implementation/MTKLAB-008.md) |
| **MTKLAB-009** | Add `004_runs.sql` Schema Migration for Run Tracking | **S** | DB Schema | MTKLAB-008 | [MTKLAB-009.md](../implementation/MTKLAB-009.md) |
| **MTKLAB-010** | Integrate Execution Run Context into Engine and CLI | **M** | Core / CLI | MTKLAB-009 | [MTKLAB-010.md](../implementation/MTKLAB-010.md) |
| **MTKLAB-011** | Update CLI `status` and `inspect` for Versions & Runs | **M** | CLI Commands | MTKLAB-010 | [MTKLAB-011.md](../implementation/MTKLAB-011.md) |

---

## 3. Detailed Issue Specifications

### MTKLAB-001: Add `002_logical_ids.sql` Migration & Storage Fixes
- **Complexity**: Small (S)
- **PR Scope**: `src/mtklab/storage/migrations/002_logical_ids.sql`, `src/mtklab/storage/db.py`, `src/mtklab/core/evidence.py`
- **Dependencies**: None
- **Spec**: [MTKLAB-001.md](../implementation/MTKLAB-001.md)

### MTKLAB-002: Add Canonical `logical_id` Helper Generator
- **Complexity**: Extra Small (XS)
- **PR Scope**: `src/mtklab/core/evidence.py`
- **Dependencies**: MTKLAB-001
- **Spec**: [MTKLAB-002.md](../implementation/MTKLAB-002.md)

### MTKLAB-003: Implement Finding Lookup and Upsert in Database
- **Complexity**: Medium (M)
- **PR Scope**: `src/mtklab/storage/db.py`
- **Dependencies**: MTKLAB-001, MTKLAB-002
- **Spec**: [MTKLAB-003.md](../implementation/MTKLAB-003.md)

### MTKLAB-004: Wire `logical_id` Deduplication in `EvidenceEngine`
- **Complexity**: Medium (M)
- **PR Scope**: `src/mtklab/core/evidence.py`
- **Dependencies**: MTKLAB-003
- **Spec**: [MTKLAB-004.md](../implementation/MTKLAB-004.md)

### MTKLAB-005: Implement Content-Addressed SHA-256 Evidence Hashing
- **Complexity**: Small (S)
- **PR Scope**: `src/mtklab/core/evidence.py`
- **Dependencies**: MTKLAB-004
- **Spec**: [MTKLAB-005.md](../implementation/MTKLAB-005.md)

### MTKLAB-006: Implement Evidence Deduplication in Storage Layer
- **Complexity**: Small (S)
- **PR Scope**: `src/mtklab/storage/db.py`
- **Dependencies**: MTKLAB-005
- **Spec**: [MTKLAB-006.md](../implementation/MTKLAB-006.md)

### MTKLAB-007: Add `003_junctions.sql` Migration for Linkage Tables
- **Complexity**: Medium (M)
- **PR Scope**: `src/mtklab/storage/migrations/003_junctions.sql`
- **Dependencies**: MTKLAB-006
- **Spec**: [MTKLAB-007.md](../implementation/MTKLAB-007.md)

### MTKLAB-008: Refactor Engine and Storage for Junction Tables
- **Complexity**: Medium (M)
- **PR Scope**: `src/mtklab/core/evidence.py`, `src/mtklab/storage/db.py`
- **Dependencies**: MTKLAB-007
- **Spec**: [MTKLAB-008.md](../implementation/MTKLAB-008.md)

### MTKLAB-009: Add `004_runs.sql` Schema Migration for Run Tracking
- **Complexity**: Small (S)
- **PR Scope**: `src/mtklab/storage/migrations/004_runs.sql`
- **Dependencies**: MTKLAB-008
- **Spec**: [MTKLAB-009.md](../implementation/MTKLAB-009.md)

### MTKLAB-010: Integrate Execution Run Context into Engine and CLI
- **Complexity**: Medium (M)
- **PR Scope**: `src/mtklab/core/context.py`, `src/mtklab/cli.py`, `src/mtklab/storage/db.py`
- **Dependencies**: MTKLAB-009
- **Spec**: [MTKLAB-010.md](../implementation/MTKLAB-010.md)

### MTKLAB-011: Update CLI `status` and `inspect` for Versions & Runs
- **Complexity**: Medium (M)
- **PR Scope**: `src/mtklab/cli.py`
- **Dependencies**: MTKLAB-010
- **Spec**: [MTKLAB-011.md](../implementation/MTKLAB-011.md)

---

## 4. Related Documents

- [RFC Document](./RFC.md)
- [Domain API Specification](./DOMAIN_API.md)
- [Implementation Roadmap](./ROADMAP.md)
- Implementation Specifications: [MTKLAB-001](../implementation/MTKLAB-001.md) through [MTKLAB-011](../implementation/MTKLAB-011.md)
