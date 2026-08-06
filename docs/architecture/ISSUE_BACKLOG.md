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
| **MTKLAB-012** | Refactor `Finding.__post_init__` to eliminate deserialization side effects | **S** | Core Domain | MTKLAB-002 | N/A (future optimization) |
| **MTKLAB-013** | Validate framework against real MT5889 firmware image | **M** | Cross-cutting | MTKLAB-011 | N/A (project milestone) |

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

### MTKLAB-012: Refactor `Finding.__post_init__` to Eliminate Deserialization Side Effects
- **Complexity**: Small (S)
- **PR Scope**: `src/mtklab/core/evidence.py`
- **Dependencies**: MTKLAB-002
- **Motivation**: MTKLAB-002 introduced `__post_init__` auto-generation of `logical_id` and automatic creation of a `"created"` version snapshot. Both `Finding.from_dict()` and `EvidenceDatabase.get_finding()` construct `Finding` objects without passing `logical_id`, triggering `__post_init__` to compute values that are then immediately overwritten. While functionally correct, this is fragile: a future deserialization path that forgets the post-construction overwrite would silently fabricate a `logical_id` for legacy records. It also wastes computation on every row-to-object conversion.
- **Proposed Approach**: Introduce a private sentinel flag (`_from_storage: bool = False`) that suppresses `__post_init__` side effects when set. Deserialization paths (`from_dict`, `get_finding`) pass `_from_storage=True` to the constructor, preventing auto-generation entirely rather than overwriting afterward.
- **Risks**: None — the current overwrite approach already works; this is a robustness and maintainability improvement only.

### MTKLAB-013: Validate Framework Against Real MT5889 Firmware Image
- **Complexity**: Medium (M)
- **PR Scope**: Cross-cutting (experiments, adapters, CLI, data)
- **Dependencies**: MTKLAB-011
- **Objective**: Ensure the framework delivers real reverse-engineering value on the actual MediaTek MT5889 projector firmware, not just infrastructure correctness on dummy data.
- **Tasks**:
  - Run `exp01_entropy_landscape` and `exp02_repeated_structures` against `data/firmware/ree_payload.bin`.
  - Verify generated findings match known structures from `config/firmware.yaml` (crypto header at 0x0, MTK binary header at 0x500, REE payload at 0x1000).
  - Add a new experiment (exp03) to parse the MTK binary header at offset 0x500 and extract partition/load-address information.
  - Add regression checks that assert the framework discovers at least the documented known structures.
- **Frequency**: Should be run periodically after each MTKLAB milestone to prevent infrastructure growth without firmware-analysis validation.

---

## 4. Related Documents

- [RFC Document](./RFC.md)
- [Domain API Specification](./DOMAIN_API.md)
- [Implementation Roadmap](./ROADMAP.md)
- Implementation Specifications: [MTKLAB-001](../implementation/MTKLAB-001.md) through [MTKLAB-011](../implementation/MTKLAB-011.md)
