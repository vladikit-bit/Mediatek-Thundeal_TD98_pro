# MTKLab Domain API Specification

## Table of Contents
- [1. Domain Overview](#1-domain-overview)
- [2. Component Responsibilities & Boundaries](#2-component-responsibilities--boundaries)
- [3. Logical ID Generation & Ownership](#3-logical-id-generation--ownership)
- [4. Finding Lifecycle & `submit_finding()` Flow](#4-finding-lifecycle--submit_finding-flow)
- [5. Inter-Experiment Communication](#5-inter-experiment-communication)
- [6. Class Invariants & Guarantees](#6-class-invariants--guarantees)
- [7. Related Documents](#7-related-documents)

---

## 1. Domain Overview

The MTKLab Domain API provides an object model for running reverse engineering experiments, collecting evidence, establishing findings, and resolving hypotheses over firmware payloads.

---

## 2. Component Responsibilities & Boundaries

| Component | Primary Responsibility | Ownership / Boundaries |
| :--- | :--- | :--- |
| **`Project`** | Manages session directory structure, configuration loading, and SQLite database connections. | Owns project root paths (`data/projects/<id>`) and DB handle lifecycle. |
| **`Experiment`** | Implements specific analysis logic (e.g., entropy calculation, repeated structure scanning). | Stateless execution unit; operates solely via `ExperimentContext`. |
| **`ExperimentContext`** | Sandboxed execution environment injected into an experiment. | Owns access to firmware files, artifact directories, and `EvidenceEngine` proxy methods. |
| **`EvidenceEngine`** | Central domain coordinator managing deduplication, versioning, and persistence. | Owns Finding identity resolution, Evidence hashing, and Hypothesis resolution. |
| **`Finding`** | Value object representing a binary discovery (region, table, offset). | Identified by stable `logical_id` and versioned `finding_id`. |
| **`Evidence`** | Value object representing a raw signal observation. | Immutable; identified by content-addressed `evidence_id` SHA-256 digest. |
| **`Hypothesis`** | Domain entity representing competing structural claims. | Owns status (`PROPOSED`, `ACCEPTED`, `REFUTED`) and evidence links. |

---

## 3. Logical ID Generation & Ownership

### 3.1 Ownership
The `EvidenceEngine` (or standard `generate_logical_id` helper) owns `logical_id` generation.

### 3.2 Canonical Format
```text
<experiment_id>:<kind>:<offset_hex>-<end_offset_hex>
```
*Example:* `exp01_entropy_landscape:region:0x00000000-0x00008000`

---

## 4. Finding Lifecycle & `submit_finding()` Flow

When `EvidenceEngine.submit_finding(finding, evidences)` is called:

1. **Logical ID Verification**: Generates or verifies `logical_id` on the incoming finding.
2. **Evidence Deduplication**: Computes content hashes for provided `Evidence` objects and inserts new records into `evidences`.
3. **Finding Lookup**: Queries database for existing records matching `logical_id`.
4. **State Comparison**:
   - **New Finding**: Assigns `version = 1`, generates new `finding_id` (UUID), inserts into `findings`.
   - **Content Unchanged**: Re-links finding to the current run without incrementing `version`.
   - **Content Modified**: Increments `version = existing_version + 1`, generates new `finding_id` (UUID), inserts snapshot into `findings`.
5. **Junction Linkage**: Inserts records into `finding_evidences` connecting `finding_id` to content-addressed `evidence_id`s.

---

## 5. Inter-Experiment Communication

- **Decoupled Execution**: Experiments must not directly import or invoke other experiments.
- **Shared Context Data**: Upstream output is passed down via `ctx.shared_data` populated by the `ExperimentRegistry` topological runner.
- **Database Queries**: Downstream experiments read persistent findings via `ctx.get_findings()` or `ctx.get_evidences()`.

---

## 6. Class Invariants & Guarantees

### 6.1 `Finding` Invariants
- `logical_id` must be non-empty and adhere to the canonical string format.
- `version` must be a positive integer ($\ge 1$).
- `confidence` must be a valid enum value (`CANDIDATE`, `PROBABLE`, `VERIFIED`, `REJECTED`, `ARCHIVED`).

### 6.2 `Evidence` Invariants
- `evidence_id` must be a valid 64-character lowercase SHA-256 hex string.
- `data` dictionary must be JSON-serializable.

### 6.3 `EvidenceEngine` Invariants
- Will never insert duplicate evidence rows for matching content hashes.
- Guaranteed atomic transactions for `submit_finding` operations.

---

## 7. Related Documents

- [RFC Document](./RFC.md)
- [Implementation Roadmap](./ROADMAP.md)
- [Issue Backlog](./ISSUE_BACKLOG.md)
- [ADR-003: Logical ID Deduplication](./ADR/ADR-003-logical-id-deduplication.md)
