# RFC: MTKLab Architecture — Evidence, Finding, and Hypothesis Model

## Table of Contents
- [1. Executive Summary](#1-executive-summary)
- [2. High-Level Architecture](#2-high-level-architecture)
- [3. Core Domain Entities & Identity](#3-core-domain-entities--identity)
- [4. Lifecycles & State Transitions](#4-lifecycles--state-transitions)
- [5. System Invariants](#5-system-invariants)
- [6. Long-Term Scalability Strategy](#6-long-term-scalability-strategy)
- [7. Related Documents](#7-related-documents)

---

## 1. Executive Summary

This Request for Comments (RFC) defines the core architecture for MTKLab, a firmware reverse engineering framework. The architecture supports long-term, incremental analysis of firmware payloads by providing deterministic deduplication, immutable evidence tracking, versioned structural findings, and hypothesis resolution.

---

## 2. High-Level Architecture

The framework decouples experiment execution from evidence storage and finding resolution:

```text
+-----------------------+      +--------------------------+
|  Experiment Plugins   | ---> |  ExperimentContext       |
+-----------------------+      +--------------------------+
                                            |
                                            v
                               +--------------------------+
                               |     EvidenceEngine       |
                               +--------------------------+
                                            |
                         +------------------+------------------+
                         |                  |                  |
                         v                  v                  v
                  +------------+     +------------+     +------------+
                  |  Evidence  |     |  Findings  |     | Hypotheses |
                  +------------+     +------------+     +------------+
                         |                  |                  |
                         +------------------+------------------+
                                            |
                                            v
                               +--------------------------+
                               |    SQLite Storage (DB)   |
                               +--------------------------+
```

---

## 3. Core Domain Entities & Identity

### 3.1 Identity Management
- **Finding Identity**: Identified by both a stable `logical_id` (e.g., `exp01:region:0x00000000-0x00008000`) representing the semantic binary concept across runs, and a `finding_id` (UUIDv4) identifying a specific snapshot version.
- **Evidence Identity**: Identified by a content-addressed SHA-256 hash (`evidence_id`) derived from its normalized payload (`experiment_id`, `evidence_type`, `source_offset`, `source_size`, `data`).
- **Run Identity**: Identified by a UUIDv4 `run_id` capturing project context, timestamp, execution flags, and configuration.

### 3.2 Domain Entities
For full API details, see [DOMAIN_API.md](./DOMAIN_API.md). Architectural decisions are detailed in [ADR Section](./ADR/).

---

## 4. Lifecycles & State Transitions

### 4.1 Finding Confidence Lifecycle
```text
[ CANDIDATE ] ---> (Multi-Signal Convergence) ---> [ PROBABLE ] ---> (Mathematical Proof) ---> [ VERIFIED ]
      |                                                 |                                          |
      +---------------------> [ REJECTED ] <------------+------------------------------------------+
                                    |
                                    v
                               [ ARCHIVED ]
```
- **CANDIDATE**: Initial weak signal.
- **PROBABLE**: Supported by multiple independent signals.
- **VERIFIED**: Proven via checksum, valid header decompression, or offset alignment.
- **REJECTED**: Contradicted by definitive proof.
- **ARCHIVED**: Obsolete or superseded version.

### 4.2 Evidence Lifecycle
- **Creation**: Produced by an experiment run.
- **Deduplication**: SHA-256 hash collision checks prevent duplicate records.
- **Immutability**: Once stored, evidence records are read-only.

---

## 5. System Invariants

1. **Evidence Immutability**: An evidence record, once created, cannot be modified or deleted.
2. **Finding Identity Stability**: The `logical_id` of a finding remains constant across runs and versions.
3. **Monotonic Versioning**: `version` numbers for a `logical_id` are strictly increasing integers ($1, 2, 3, \dots$).
4. **Relational Integrity**: Junction tables handle many-to-many links between Findings, Evidence, and Hypotheses (`PRAGMA foreign_keys = ON`).
5. **Run Context Tracing**: Every experiment execution record links to a parent session `run_id`.

---

## 6. Long-Term Scalability Strategy

- **Deduplication at Storage Boundary**: Duplicate evidence payloads are discarded at insert time using content-addressed hashes.
- **Version Snapshotting**: Re-running experiments on identical binary inputs produces no new version entries unless attributes change.
- **Indexed Relational Lookups**: Core queries rely on indexed columns (`logical_id`, `evidence_id`, `run_id`).

---

## 7. Related Documents

- [Domain API Specification](./DOMAIN_API.md)
- [Implementation Roadmap](./ROADMAP.md)
- [Issue Backlog](./ISSUE_BACKLOG.md)
- Architecture Decision Records:
  - [ADR-001: Runs & Executions](./ADR/ADR-001-runs-and-executions.md)
  - [ADR-002: Content-Addressed Evidence](./ADR/ADR-002-content-addressed-evidence.md)
  - [ADR-003: Logical ID Deduplication](./ADR/ADR-003-logical-id-deduplication.md)
  - [ADR-004: SQLite Schema Evolution](./ADR/ADR-004-sqlite-schema-evolution.md)
