# ADR-002: Content-Addressed Evidence Identification

## Table of Contents
- [1. Context](#1-context)
- [2. Decision](#2-decision)
- [3. Consequences](#3-consequences)
- [4. Related Documents](#4-related-documents)

---

## 1. Context
Evidence records were previously assigned random UUIDs, causing duplicate storage when identical evidence was submitted across multiple runs or experiments.

---

## 2. Decision
We replace random UUIDs with SHA-256 content hashes derived from normalized evidence fields:
- Payload fields hashed: `experiment_id`, `evidence_type`, `source_offset`, `source_size`, `data`.
- Formatting: 64-character lowercase hexadecimal string.

---

## 3. Consequences
### Positive
- Automatic storage deduplication across experiments and runs.
- Guarantees evidence immutability.

### Negative
- CPU overhead for computing SHA-256 digests (negligible for expected data scale).

---

## 4. Related Documents
- [RFC Document](../RFC.md)
- [Domain API Specification](../DOMAIN_API.md)
- [MTKLAB-005 Specification](../../implementation/MTKLAB-005.md)
- [MTKLAB-006 Specification](../../implementation/MTKLAB-006.md)
