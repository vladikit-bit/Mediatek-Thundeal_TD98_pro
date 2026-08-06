# ADR-004: SQLite Schema Evolution Strategy

## Table of Contents
- [1. Context](#1-context)
- [2. Decision](#2-decision)
- [3. Consequences](#3-consequences)
- [4. Related Documents](#4-related-documents)

---

## 1. Context
MTKLab uses per-project SQLite databases (`data/projects/<id>/evidence.db`). As the data model evolves across framework versions, existing project databases must upgrade seamlessly without data loss.

---

## 2. Decision
We implement a strictly versioned, migration-file-driven schema evolution model:
- `schema_migrations` table tracks applied version integers.
- Sequential SQL files (`001_initial.sql`, `002_logical_ids.sql`, `003_junctions.sql`, `004_runs.sql`) are automatically applied on database connection initialization.
- Schema changes utilize SQLite-compatible `ALTER TABLE` statements and transaction safeguards.

---

## 3. Consequences
### Positive
- Fully backward-compatible upgrade path for existing user project databases.
- Automated migration application on framework launch.

### Negative
- SQLite syntax limitations require careful migration script design (e.g., column addition constraints).

---

## 4. Related Documents
- [RFC Document](../RFC.md)
- [Implementation Roadmap](../ROADMAP.md)
- [MTKLAB-001 Specification](../../implementation/MTKLAB-001.md)
- [MTKLAB-007 Specification](../../implementation/MTKLAB-007.md)
- [MTKLAB-009 Specification](../../implementation/MTKLAB-009.md)
