# Code Review Guidelines

## Table of Contents
- [1. Maintainer Philosophy](#1-maintainer-philosophy)
- [2. Code Review Focus Areas](#2-code-review-focus-areas)
- [3. Review Process & Severity Labels](#3-review-process--severity-labels)
- [4. Definition of Done](#4-definition-of-done)
- [5. Related Documents](#5-related-documents)

---

## 1. Maintainer Philosophy

Code reviews in MTKLab serve to preserve architectural integrity, ensure backward compatibility across firmware project databases, and maintain clean, testable Python code.

---

## 2. Code Review Focus Areas

### 2.1 Architectural Conformance
Verify that PRs do not violate invariants specified in [RFC.md](../architecture/RFC.md) or approved ADRs:
- Evidence objects must be immutable and content-addressed via SHA-256 (`evidence_id`).
- Findings must maintain a stable `logical_id` across runs and versions.
- Data modifications must go through `EvidenceEngine` rather than direct database manipulation in experiments.

### 2.2 Storage & Migration Integrity
- Review SQL migration scripts for SQLite compatibility.
- Ensure `INSERT OR REPLACE` is not used where it could trigger unexpected cascading deletes. Prefer `INSERT OR IGNORE` for deduplicated content.
- Confirm schema version tracking in `schema_migrations` table is correctly handled.

### 2.3 Backward & Forward Compatibility
- Ensure existing user project databases (`data/projects/<id>/evidence.db`) automatically migrate without error or data loss.
- Verify serialization methods (`to_dict()`, `from_dict()`) maintain default fallbacks for missing keys.

---

## 3. Review Process & Severity Labels

Review feedback must categorize issues clearly:
- **[BLOCKER]**: Architectural violation, breaking change, missing test, or migration failure. Must be resolved before merge.
- **[RECOMMENDED]**: Code readability or performance improvement. Highly recommended.
- **[NITPICK]**: Minor stylistic preference. Optional.

---

## 4. Definition of Done

A pull request is ready to merge when:
1. All items in [PR_CHECKLIST.md](./PR_CHECKLIST.md) are checked.
2. All automated tests (`pytest`) pass green.
3. No [BLOCKER] review comments remain.
4. Approved by at least one maintainer.

---

## 5. Related Documents

- [PR Quality Checklist](./PR_CHECKLIST.md)
- [RFC Document](../architecture/RFC.md)
- [Domain API Specification](../architecture/DOMAIN_API.md)
