# Pull Request Quality Checklist

## Table of Contents
- [1. General Principles](#1-general-principles)
- [2. Pre-Submission Checklist](#2-pre-submission-checklist)
- [3. Automated Verification Commands](#3-automated-verification-commands)
- [4. Related Documents](#4-related-documents)

---

## 1. General Principles

Every PR merged into MTKLab must maintain the integrity of the project, adhere to architectural decisions, and pass all automated quality checks.

---

## 2. Pre-Submission Checklist

### 2.1 Scope & Architecture
- [ ] PR addresses exactly one ticket/issue scope.
- [ ] Code modifications conform to approved architecture and ADR decisions.
- [ ] No unrequested features, speculative abstractions, or API redesigns introduced.

### 2.2 Code Quality & Formatting
- [ ] Code written in clean, type-annotated Python 3.10+.
- [ ] Formatted using Black and standard linting tools.
- [ ] All new functions and public classes include standard docstrings.

### 2.3 Storage & Migrations
- [ ] SQL migrations use clean `0XX_*.sql` naming convention.
- [ ] Migration scripts use `IF NOT EXISTS` guards and SQLite-compatible syntax.
- [ ] Foreign keys enforced (`PRAGMA foreign_keys = ON`).

### 2.4 Testing & Verification
- [ ] Unit tests added or updated for all modified functions.
- [ ] All tests pass locally using `PYTHONPATH=src pytest`.
- [ ] Edge cases (e.g., `None` values, duplicate inserts) covered by tests.

---

## 3. Automated Verification Commands

Run the following commands prior to submitting your PR:

```bash
# Set PYTHONPATH to src directory
export PYTHONPATH=src

# Run unit and integration test suite
pytest

# Verify code formatting and linting
black --check src/ tests/
flake8 src/ tests/
```

---

## 4. Related Documents

- [Review Guidelines](./REVIEW_GUIDELINES.md)
- [Issue Backlog](../architecture/ISSUE_BACKLOG.md)
- [RFC Document](../architecture/RFC.md)
