"""Evidence system: Candidate → Probable → Verified lifecycle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConfidenceLevel(Enum):
    """Confidence levels for evidence and findings."""

    CANDIDATE = 1  # Single weak signal
    PROBABLE = 2  # Multiple independent signals converging
    VERIFIED = 3  # Mathematically proven (CRC, decompression, structural validation)

    def __ge__(self, other: "ConfidenceLevel") -> bool:
        if not isinstance(other, ConfidenceLevel):
            return NotImplemented
        return self.value >= other.value

    def __gt__(self, other: "ConfidenceLevel") -> bool:
        if not isinstance(other, ConfidenceLevel):
            return NotImplemented
        return self.value > other.value

    def __str__(self) -> str:
        return self.name


class EvidenceType(Enum):
    """Types of evidence that can support findings."""

    SIGNATURE_MATCH = "signature_match"
    ENTROPY_BOUNDARY = "entropy_boundary"
    STRUCTURAL_PATTERN = "structural_pattern"
    CRC_VALIDATION = "crc_validation"
    DECOMPRESSION_SUCCESS = "decompression_success"
    OFFSET_REFERENCE = "offset_reference"
    ALIGNMENT_PATTERN = "alignment_pattern"
    STRING_CLUSTER = "string_cluster"
    HEADER_SIMILARITY = "header_similarity"
    FIELD_STATISTICS = "field_statistics"
    CROSS_REFERENCE = "cross_reference"
    MANUAL_ANNOTATION = "manual_annotation"

    def __str__(self) -> str:
        return self.value


class FindingKind(Enum):
    """Kinds of structural findings."""

    REGION = "region"
    OBJECT = "object"
    TABLE = "table"
    HEADER = "header"
    BOUNDARY = "boundary"
    STREAM = "stream"
    PARTITION = "partition"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


@dataclass
class Evidence:
    """Single piece of evidence supporting/refuting a hypothesis."""

    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str = ""
    evidence_type: EvidenceType = EvidenceType.SIGNATURE_MATCH
    confidence: ConfidenceLevel = ConfidenceLevel.CANDIDATE
    description: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    source_offset: int | None = None
    source_size: int | None = None
    tags: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "experiment_id": self.experiment_id,
            "evidence_type": str(self.evidence_type),
            "confidence": self.confidence.name,
            "description": self.description,
            "data": self.data,
            "source_offset": self.source_offset,
            "source_size": self.source_size,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        return cls(
            evidence_id=d["evidence_id"],
            experiment_id=d["experiment_id"],
            evidence_type=EvidenceType(d["evidence_type"]),
            confidence=ConfidenceLevel[d["confidence"]],
            description=d["description"],
            data=d["data"],
            source_offset=d.get("source_offset"),
            source_size=d.get("source_size"),
            tags=d.get("tags", []),
            timestamp=datetime.fromisoformat(d["timestamp"]),
        )


@dataclass
class Finding:
    """A structural finding in the firmware (region, object, table, etc.)."""

    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str = ""
    kind: FindingKind = FindingKind.UNKNOWN
    offset: int = 0
    size: int | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.CANDIDATE
    label: str | None = None
    description: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Versioned history - first-class feature
    versions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.versions:
            self.versions.append(self._create_version_snapshot("created"))

    def _create_version_snapshot(self, reason: str) -> dict[str, Any]:
        return {
            "version": len(self.versions) + 1,
            "confidence": self.confidence.name,
            "label": self.label,
            "description": self.description,
            "evidence_ids": list(self.evidence_ids),
            "metadata": dict(self.metadata),
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def add_evidence(self, evidence_id: str, evidence_engine: "EvidenceEngine" = None):
        """Add supporting evidence and recalculate confidence."""
        if evidence_id not in self.evidence_ids:
            self.evidence_ids.append(evidence_id)
            if evidence_engine:
                # Engine will recalculate confidence
                pass
            else:
                self._recalculate_confidence()

    def upgrade_confidence(self, new_confidence: ConfidenceLevel, reason: str, evidence_engine: "EvidenceEngine" = None):
        """Explicitly upgrade confidence with version tracking."""
        if new_confidence > self.confidence:
            old = self.confidence
            self.confidence = new_confidence
            self.versions.append(self._create_version_snapshot(f"upgrade: {reason} ({old.name} → {new_confidence.name})"))

    def set_label(self, label: str, reason: str):
        """Update label with version tracking."""
        if label != self.label:
            self.label = label
            self.versions.append(self._create_version_snapshot(f"label_change: {reason}"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "experiment_id": self.experiment_id,
            "kind": str(self.kind),
            "offset": self.offset,
            "size": self.size,
            "confidence": self.confidence.name,
            "label": self.label,
            "description": self.description,
            "evidence_ids": self.evidence_ids,
            "metadata": self.metadata,
            "versions": self.versions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        f = cls(
            finding_id=d["finding_id"],
            experiment_id=d["experiment_id"],
            kind=FindingKind(d["kind"]),
            offset=d["offset"],
            size=d.get("size"),
            confidence=ConfidenceLevel[d["confidence"]],
            label=d.get("label"),
            description=d.get("description", ""),
            evidence_ids=d.get("evidence_ids", []),
            metadata=d.get("metadata", {}),
        )
        f.versions = d.get("versions", [])
        return f


class EvidenceEngine:
    """
    Central authority for evidence lifecycle: Candidate → Probable → Verified.
    All experiments submit findings through this engine.
    """

    def __init__(self, db: "EvidenceDatabase"):
        self.db = db

    def submit_finding(self, finding: Finding, evidences: list[Evidence]) -> Finding:
        """Register finding + evidence, upgrade confidence if warranted."""
        # Store evidences
        for ev in evidences:
            self.db.store_evidence(ev)
            if ev.evidence_id not in finding.evidence_ids:
                finding.evidence_ids.append(ev.evidence_id)

        # Determine confidence from evidence
        finding.confidence = self._calculate_confidence(evidences)
        finding.versions.append(finding._create_version_snapshot("initial_submission"))

        # Store finding
        self.db.store_finding(finding)

        # Check for related hypotheses
        self._update_hypotheses(finding)

        return finding

    def _calculate_confidence(self, evidences: list[Evidence]) -> ConfidenceLevel:
        """Upgrade logic based on evidence diversity and strength."""
        if not evidences:
            return ConfidenceLevel.CANDIDATE

        # Count unique evidence types
        types = set(e.evidence_type for e in evidences)

        # VERIFIED: Mathematical proof (CRC, successful decompression)
        if any(
            e.evidence_type
            in (EvidenceType.CRC_VALIDATION, EvidenceType.DECOMPRESSION_SUCCESS)
            for e in evidences
        ):
            return ConfidenceLevel.VERIFIED

        # PROBABLE: Multiple independent evidence types converging
        if len(types) >= 2:
            return ConfidenceLevel.PROBABLE

        return ConfidenceLevel.CANDIDATE

    def upgrade_finding(self, finding_id: str, new_confidence: ConfidenceLevel, reason: str):
        """Explicit upgrade (e.g., after manual review)."""
        finding = self.db.get_finding(finding_id)
        if not finding:
            raise KeyError(f"Finding {finding_id} not found")
        old = finding.confidence
        finding.confidence = new_confidence
        finding.versions.append(
            finding._create_version_snapshot(f"manual_upgrade: {reason} ({old.name} → {new_confidence.name})")
        )
        self.db.update_finding(finding)

    def _update_hypotheses(self, finding: Finding):
        """Update any hypotheses related to this finding's offset range."""
        from .hypothesis import Hypothesis, HypothesisStatus

        # Find hypotheses that overlap with this finding
        hypotheses = self.db.get_hypotheses_for_offset(finding.offset, finding.size)
        for hyp in hypotheses:
            # Check if finding supports or contradicts
            if self._finding_supports_hypothesis(finding, hyp):
                if finding.finding_id not in hyp.supporting_evidence:
                    hyp.supporting_evidence.append(finding.finding_id)
            elif self._finding_contradicts_hypothesis(finding, hyp):
                if finding.finding_id not in hyp.contradicting_evidence:
                    hyp.contradicting_evidence.append(finding.finding_id)
            hyp._recalculate_status()
            self.db.update_hypothesis(hyp)

    def _finding_supports_hypothesis(self, finding: Finding, hypothesis: "Hypothesis") -> bool:
        """Heuristic: does this finding support the hypothesis?"""
        # Simple implementation - can be extended
        return finding.offset >= hypothesis.subject_offset and (
            hypothesis.subject_size is None
            or finding.offset < hypothesis.subject_offset + hypothesis.subject_size
        )

    def _finding_contradicts_hypothesis(self, finding: Finding, hypothesis: "Hypothesis") -> bool:
        """Heuristic: does this finding contradict the hypothesis?"""
        # If finding has a label that contradicts hypothesis claim
        if finding.label and hypothesis.claim:
            # Very simple - in reality would need NLP or structured claims
            return False
        return False