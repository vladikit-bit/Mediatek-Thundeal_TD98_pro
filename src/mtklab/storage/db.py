"""SQLite-backed storage for the Evidence Engine."""

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mtklab.core.evidence import ConfidenceLevel, Evidence, EvidenceType, Finding, FindingKind
from mtklab.core.hypothesis import Hypothesis, HypothesisStatus
# Note: ExperimentResult is loaded dynamically to avoid circular imports where possible,
# but we can import it for typing if needed.
from mtklab.utils import json
from mtklab.storage.migrations import MigrationManager

logger = logging.getLogger(__name__)


class EvidenceDatabase:
    """
    SQLite-backed database for tracking experiments, evidence, findings, and hypotheses.
    
    Designed as a facade over the database. In the future, this can be split into
    separate Repository classes (EvidenceRepository, FindingRepository, etc.) 
    without breaking the public API.
    """

    def __init__(self, db_path: Path, migrations_dir: Path):
        """
        Initialize the database and apply any pending migrations.
        
        Args:
            db_path: Path to the SQLite database file.
            migrations_dir: Path to the directory containing .sql migrations.
        """
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        
        # Apply migrations
        migrator = MigrationManager(self._conn, migrations_dir)
        migrator.apply_migrations()

    def close(self):
        """Close the database connection."""
        self._conn.close()

    # --- Evidence Operations ---

    def store_evidence(self, evidence: Evidence) -> bool:
        """Store a single piece of evidence using INSERT OR IGNORE.

        Returns True if a new row was inserted, False if it was ignored
        because an evidence record with the same (content-addressed, since
        MTKLAB-005) evidence_id already exists -- i.e. this exact evidence
        was already recorded, possibly by an earlier run or experiment
        (ADR-002 automatic deduplication).
        """
        # Ensure UUIDs are strings
        if not isinstance(evidence.evidence_id, str):
            evidence.evidence_id = str(evidence.evidence_id)
            
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO evidences (
                    evidence_id, experiment_id, evidence_type, confidence, 
                    description, data_json, source_offset, source_size, 
                    tags_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    evidence.experiment_id,
                    str(evidence.evidence_type),
                    evidence.confidence.name,
                    evidence.description,
                    json.dumps(evidence.data),
                    evidence.source_offset,
                    evidence.source_size,
                    json.dumps(evidence.tags),
                    evidence.timestamp.isoformat(),
                )
            )
            return cursor.rowcount > 0

    def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        """Retrieve evidence by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM evidences WHERE evidence_id = ?", 
            (str(evidence_id),)
        )
        row = cursor.fetchone()
        if not row:
            return None
            
        return Evidence(
            evidence_id=row["evidence_id"],
            experiment_id=row["experiment_id"],
            evidence_type=EvidenceType(row["evidence_type"]),
            confidence=ConfidenceLevel[row["confidence"]],
            description=row["description"],
            data=json.loads(row["data_json"]),
            source_offset=row["source_offset"],
            source_size=row["source_size"],
            tags=json.loads(row["tags_json"]),
            timestamp=datetime.fromisoformat(row["timestamp"])
        )

    # --- Junction Operations (MTKLAB-007/008) ---

    def link_finding_evidences(self, finding_id: str, evidence_ids: List[str]) -> None:
        """Record finding<->evidence links in the normalized junction table.

        Both finding_id and every evidence_id must already exist in their
        respective tables (finding_evidences has ON DELETE CASCADE foreign
        keys to findings/evidences, and PRAGMA foreign_keys=ON is set on
        this connection -- see __init__), so this must only be called after
        store_finding()/store_evidence() for the referenced rows. Safe to
        call with an empty list (no-ops). INSERT OR IGNORE makes re-linking
        an already-linked pair a harmless no-op, matching the composite
        PRIMARY KEY (finding_id, evidence_id).
        """
        if not evidence_ids:
            return
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            for eid in evidence_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO finding_evidences (finding_id, evidence_id) VALUES (?, ?)",
                    (finding_id, str(eid)),
                )

    def get_evidences_for_finding(self, finding_id: str) -> List[Evidence]:
        """Retrieve all evidence linked to a finding via the normalized
        finding_evidences junction table (MTKLAB-008), not the deprecated
        evidence_ids_json column on findings."""
        cursor = self._conn.execute(
            """
            SELECT e.* FROM evidences e
            JOIN finding_evidences fe ON fe.evidence_id = e.evidence_id
            WHERE fe.finding_id = ?
            ORDER BY fe.created_at
            """,
            (finding_id,),
        )
        return [
            Evidence(
                evidence_id=row["evidence_id"],
                experiment_id=row["experiment_id"],
                evidence_type=EvidenceType(row["evidence_type"]),
                confidence=ConfidenceLevel[row["confidence"]],
                description=row["description"],
                data=json.loads(row["data_json"]),
                source_offset=row["source_offset"],
                source_size=row["source_size"],
                tags=json.loads(row["tags_json"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in cursor.fetchall()
        ]

    # --- Finding Operations ---

    def store_finding(self, finding: Finding) -> None:
        """Store a new finding."""
        if not isinstance(finding.finding_id, str):
            finding.finding_id = str(finding.finding_id)
            
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT OR IGNORE INTO findings (
                    finding_id, experiment_id, kind, offset, size, 
                    confidence, label, description, evidence_ids_json, 
                    metadata_json, versions_json, logical_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    finding.experiment_id,
                    str(finding.kind),
                    finding.offset,
                    finding.size,
                    finding.confidence.name,
                    finding.label,
                    finding.description,
                    json.dumps(finding.evidence_ids),
                    json.dumps(finding.metadata),
                    json.dumps(finding.versions),
                    finding.logical_id,
                )
            )

    def update_finding(self, finding: Finding) -> None:
        """Update an existing finding."""
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                UPDATE findings SET
                    confidence = ?, label = ?, description = ?,
                    evidence_ids_json = ?, metadata_json = ?, versions_json = ?
                WHERE finding_id = ?
                """,
                (
                    finding.confidence.name,
                    finding.label,
                    finding.description,
                    json.dumps(finding.evidence_ids),
                    json.dumps(finding.metadata),
                    json.dumps(finding.versions),
                    str(finding.finding_id),
                )
            )

    def _row_to_finding(self, row: sqlite3.Row) -> Finding:
        """Convert a database row into a Finding object.

        MTKLAB-012: constructed with _from_storage=True so
        Finding.__post_init__'s logical_id/version auto-generation
        (MTKLAB-002) never fires here at all -- no construct-then-overwrite
        step. A row's logical_id column is the source of truth for what was
        actually persisted/indexed; rows written before migration 002 (or
        before MTKLAB-002 shipped) legitimately have NULL, and this must
        reflect that exactly rather than fabricate a value that was never
        stored or deduplicated on.
        """
        return Finding(
            finding_id=row["finding_id"],
            experiment_id=row["experiment_id"],
            kind=FindingKind(row["kind"]),
            offset=row["offset"],
            size=row["size"],
            confidence=ConfidenceLevel[row["confidence"]],
            label=row["label"],
            description=row["description"],
            evidence_ids=json.loads(row["evidence_ids_json"]),
            metadata=json.loads(row["metadata_json"]),
            logical_id=row["logical_id"] if "logical_id" in row.keys() else None,
            versions=json.loads(row["versions_json"]),
            _from_storage=True,
        )

    def get_finding(self, finding_id: str) -> Optional[Finding]:
        """Retrieve a finding by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM findings WHERE finding_id = ?",
            (str(finding_id),)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_finding(row)

    def get_latest_finding_by_logical_id(self, logical_id: str) -> Optional[Finding]:
        """Retrieve the highest-version finding for a given ``logical_id``.

        Multiple rows in the ``findings`` table can share the same
        ``logical_id`` (each representing a version snapshot with its own
        ``finding_id`` UUID).  This method returns the row whose latest
        version number — parsed from the ``versions_json`` column — is the
        greatest.

        Returns ``None`` when no finding with the given ``logical_id``
        exists (including rows where ``logical_id`` is NULL).
        """
        cursor = self._conn.execute(
            "SELECT * FROM findings WHERE logical_id = ?",
            (logical_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            return None

        def _latest_version(row: sqlite3.Row) -> int:
            """Extract the highest version number from a row's versions_json."""
            try:
                versions = json.loads(row["versions_json"])
            except (json.JSONDecodeError, TypeError):
                # Unparseable or missing versions_json: default to version 1
                # per MTKLAB-003 edge-case specification.
                return 1
            if versions:
                return versions[-1].get("version", 1)
            # Empty versions array: default to version 1
            return 1

        latest_row = max(rows, key=_latest_version)
        return self._row_to_finding(latest_row)

    # --- Hypothesis Operations ---

    def store_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store a new hypothesis."""
        if not isinstance(hypothesis.hypothesis_id, str):
            hypothesis.hypothesis_id = str(hypothesis.hypothesis_id)
            
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT OR IGNORE INTO hypotheses (
                    hypothesis_id, subject_offset, subject_size, claim, 
                    alternative_claims_json, status, supporting_evidence_json, 
                    contradicting_evidence_json, resolved_claim, resolution_reason, 
                    confidence, versions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.hypothesis_id,
                    hypothesis.subject_offset,
                    hypothesis.subject_size,
                    hypothesis.claim,
                    json.dumps(hypothesis.alternative_claims),
                    hypothesis.status.value,
                    json.dumps(hypothesis.supporting_evidence),
                    json.dumps(hypothesis.contradicting_evidence),
                    hypothesis.resolved_claim,
                    hypothesis.resolution_reason,
                    hypothesis.confidence.name,
                    json.dumps(hypothesis.versions),
                )
            )

    def update_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Update an existing hypothesis."""
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                UPDATE hypotheses SET
                    claim = ?, alternative_claims_json = ?, status = ?,
                    supporting_evidence_json = ?, contradicting_evidence_json = ?,
                    resolved_claim = ?, resolution_reason = ?, confidence = ?,
                    versions_json = ?
                WHERE hypothesis_id = ?
                """,
                (
                    hypothesis.claim,
                    json.dumps(hypothesis.alternative_claims),
                    hypothesis.status.value,
                    json.dumps(hypothesis.supporting_evidence),
                    json.dumps(hypothesis.contradicting_evidence),
                    hypothesis.resolved_claim,
                    hypothesis.resolution_reason,
                    hypothesis.confidence.name,
                    json.dumps(hypothesis.versions),
                    str(hypothesis.hypothesis_id),
                )
            )

    def get_hypotheses_for_offset(self, offset: int, size: Optional[int] = None) -> List[Hypothesis]:
        """Get all hypotheses that apply to a specific offset."""
        # A simple overlap query. In practice, subject_size can be null.
        cursor = self._conn.execute(
            """
            SELECT * FROM hypotheses 
            WHERE subject_offset <= ? 
              AND (subject_size IS NULL OR (subject_offset + subject_size) > ?)
            """,
            (offset, offset)
        )
        
        hypotheses = []
        for row in cursor.fetchall():
            h = Hypothesis(
                hypothesis_id=row["hypothesis_id"],
                subject_offset=row["subject_offset"],
                subject_size=row["subject_size"],
                claim=row["claim"],
                alternative_claims=json.loads(row["alternative_claims_json"]),
                status=HypothesisStatus(row["status"]),
                supporting_evidence=json.loads(row["supporting_evidence_json"]),
                contradicting_evidence=json.loads(row["contradicting_evidence_json"]),
                resolved_claim=row["resolved_claim"],
                resolution_reason=row["resolution_reason"],
                confidence=ConfidenceLevel[row["confidence"]],
            )
            h.versions = json.loads(row["versions_json"])
            hypotheses.append(h)
            
        return hypotheses

    # --- Run Tracking Operations (MTKLAB-009/010) ---

    def create_run(self, run_id: str, project_id: str, command: str = "", config: Optional[Dict[str, Any]] = None) -> None:
        """Record a new execution session (parent 'runs' row).

        Must be called before record_experiment_run() for the same run_id:
        experiment_runs.run_id has an ON DELETE CASCADE foreign key to
        runs(run_id), enforced by PRAGMA foreign_keys=ON (see __init__).
        """
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                "INSERT INTO runs (run_id, project_id, command, config_json) VALUES (?, ?, ?, ?)",
                (run_id, project_id, command, json.dumps(config or {})),
            )

    def record_experiment_run(
        self,
        run_id: str,
        experiment_id: str,
        status: str,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a single experiment's outcome within a run.

        Status is application-defined (SUCCESS, FAILED, CANCELLED, RUNNING,
        etc. -- see MTKLAB-009 section 8; intentionally unconstrained at the
        DB level). Returns the generated experiment_run_id.
        """
        experiment_run_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT INTO experiment_runs (
                    experiment_run_id, run_id, experiment_id, status,
                    error_message, duration_seconds, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_run_id,
                    run_id,
                    experiment_id,
                    status,
                    error_message,
                    duration_seconds,
                    json.dumps(metrics or {}),
                ),
            )
        return experiment_run_id

    def count_runs(self) -> int:
        """Total number of recorded execution sessions."""
        cursor = self._conn.execute("SELECT COUNT(*) AS c FROM runs")
        return cursor.fetchone()["c"]

    def get_run_experiment_runs(self, run_id: str) -> List[Dict[str, Any]]:
        """All experiment_runs rows for a given run_id, most recent first."""
        cursor = self._conn.execute(
            "SELECT * FROM experiment_runs WHERE run_id = ? ORDER BY created_at DESC",
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # --- Experiment Result & Artifact Operations ---

    def store_experiment_result(self, result: Any) -> None:
        """Store the high-level result of an experiment."""
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT OR REPLACE INTO experiments (
                    experiment_id, display_name, version, status, started_at,
                    completed_at, summary, parameters_json, metadata_json, errors_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.experiment_id,
                    getattr(result, "display_name", result.experiment_id),
                    getattr(result, "version", "1.0.0"),
                    result.status,
                    result.started_at.isoformat(),
                    result.completed_at.isoformat() if result.completed_at else None,
                    result.summary,
                    json.dumps(getattr(result, "parameters", {})),
                    json.dumps(result.metadata),
                    json.dumps(result.errors),
                )
            )

    def store_artifact_reference(self, experiment_id: str, artifact_type: str, file_path: Path, description: str = "") -> str:
        """Store a reference to a file artifact."""
        artifact_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT INTO experiment_artifacts (
                    artifact_id, experiment_id, artifact_type, file_path, 
                    description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    experiment_id,
                    artifact_type,
                    str(file_path),
                    description,
                    datetime.utcnow().isoformat(),
                )
            )
        return artifact_id

    def get_experiment_artifacts(self, experiment_id: str) -> Dict[str, Path]:
        """Get all artifact paths for an experiment."""
        cursor = self._conn.execute(
            "SELECT artifact_type, file_path FROM experiment_artifacts WHERE experiment_id = ?",
            (experiment_id,)
        )
        return {row["artifact_type"]: Path(row["file_path"]) for row in cursor.fetchall()}
