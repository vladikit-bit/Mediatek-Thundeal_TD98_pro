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
        
        # Apply migrations
        migrator = MigrationManager(self._conn, migrations_dir)
        migrator.apply_migrations()

    def close(self):
        """Close the database connection."""
        self._conn.close()

    # --- Evidence Operations ---

    def store_evidence(self, evidence: Evidence) -> None:
        """Store a single piece of evidence."""
        # Ensure UUIDs are strings
        if not isinstance(evidence.evidence_id, str):
            evidence.evidence_id = str(evidence.evidence_id)
            
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT INTO evidences (
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

    # --- Finding Operations ---

    def store_finding(self, finding: Finding) -> None:
        """Store a new finding."""
        if not isinstance(finding.finding_id, str):
            finding.finding_id = str(finding.finding_id)
            
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT INTO findings (
                    finding_id, experiment_id, kind, offset, size, 
                    confidence, label, description, evidence_ids_json, 
                    metadata_json, versions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def get_finding(self, finding_id: str) -> Optional[Finding]:
        """Retrieve a finding by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM findings WHERE finding_id = ?", 
            (str(finding_id),)
        )
        row = cursor.fetchone()
        if not row:
            return None
            
        finding = Finding(
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
        )
        finding.versions = json.loads(row["versions_json"])
        return finding

    # --- Hypothesis Operations ---

    def store_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store a new hypothesis."""
        if not isinstance(hypothesis.hypothesis_id, str):
            hypothesis.hypothesis_id = str(hypothesis.hypothesis_id)
            
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT INTO hypotheses (
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
