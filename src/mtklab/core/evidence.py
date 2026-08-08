"""Evidence system: Candidate → Probable → Verified lifecycle."""

from __future__ import annotations

import hashlib
import json
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

    # None by default (not a random UUID via default_factory) so
    # __post_init__ can distinguish "not explicitly provided" and populate
    # it with a deterministic content hash instead (MTKLAB-005 / ADR-002).
    # Every current reconstruction path (from_dict's required "evidence_id"
    # key, db.get_evidence()'s NOT-NULL-in-practice primary key column)
    # always supplies a real, non-None value explicitly, so this does not
    # carry the same reconstruction-path risk that Finding.logical_id's
    # auto-population had (see MTKLAB-002): there is no legacy NULL
    # evidence_id anywhere to accidentally overwrite.
    evidence_id: str | None = None
    experiment_id: str = ""
    evidence_type: EvidenceType = EvidenceType.SIGNATURE_MATCH
    confidence: ConfidenceLevel = ConfidenceLevel.CANDIDATE
    description: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    source_offset: int | None = None
    source_size: int | None = None
    tags: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.evidence_id is None:
            self.evidence_id = self.compute_content_hash()

    def compute_content_hash(self) -> str:
        """Compute a deterministic SHA-256 hash of this evidence's payload.

        Two Evidence objects with identical (experiment_id, evidence_type,
        source_offset, source_size, data) hash identically regardless of
        when they were created or in what dict-key order `data` happens to
        be -- this is what lets storage-layer INSERT OR IGNORE (MTKLAB-006)
        naturally deduplicate the same evidence submitted across multiple
        runs/experiments (ADR-002). `timestamp` is deliberately NOT part of
        the hash: including it would make every submission unique and
        defeat deduplication entirely.
        """
        data_str = json.dumps(self.data, sort_keys=True)
        canonical = f"{self.experiment_id}:{self.evidence_type}:{self.source_offset}:{self.source_size}:{data_str}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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


def generate_logical_id(
    experiment_id: str, kind: str, offset: int | None, size: int | None
) -> str:
    """Generate the canonical ``logical_id`` string for a Finding.

    Format: ``<experiment_id>:<kind>:0x<offset>-0x<end_offset>`` with offsets
    zero-padded to 8 hex digits, or ``<experiment_id>:<kind>:global`` when
    ``offset`` or ``size`` is unknown.

    See DOMAIN_API.md section 3.2 ("Canonical Format") for the specification.

    Args:
        experiment_id: Owning experiment identifier (e.g. "exp01_entropy_landscape").
        kind: Finding kind as a string (e.g. "region", "header").
        offset: Start offset in the binary, or None if not region-scoped.
        size: Size in bytes, or None if not region-scoped.

    Returns:
        A deterministic, human-readable logical_id string.
    """
    if offset is None or size is None:
        return f"{experiment_id}:{kind}:global"
    end_offset = offset + size
    return f"{experiment_id}:{kind}:0x{offset:08x}-0x{end_offset:08x}"


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
    logical_id: str | None = None

    # Versioned history - first-class feature
    versions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.logical_id is None:
            self.logical_id = generate_logical_id(
                self.experiment_id, str(self.kind), self.offset, self.size
            )
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

    def add_version(self, reason: str = "") -> dict[str, Any]:
        """Add a new version snapshot to the version history.

        Creates a snapshot of the current finding state and appends it to
        ``self.versions`` with a monotonically increasing version number
        (derived from ``len(self.versions) + 1``).

        Args:
            reason: Human-readable reason for the version change.

        Returns:
            The created version snapshot dictionary.
        """
        snapshot = self._create_version_snapshot(reason)
        self.versions.append(snapshot)
        return snapshot

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
            "logical_id": self.logical_id,
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
        # Deserialization restores exactly what was persisted, including a
        # missing/None logical_id for pre-MTKLAB-002 records. It must NOT go
        # through the __post_init__ auto-generation path, or legacy records
        # would silently acquire a fabricated logical_id that was never
        # actually indexed/deduplicated on. See MTKLAB-001 edge cases and
        # REVIEW_GUIDELINES.md 2.3 ("maintain default fallbacks for missing keys").
        f.logical_id = d.get("logical_id")
        f.versions = d.get("versions", [])
        return f


class EvidenceEngine:
    """
    Central authority for evidence lifecycle: Candidate → Probable → Verified.
    All experiments submit findings through this engine.
    """

    def __init__(self, db: "EvidenceDatabase"):
        self.db = db

    def submit_finding(self, finding: Finding, evidences: list[Evidence] | None = None) -> Finding:
        """Register finding + evidence with logical_id deduplication and versioning.

        Workflow per DOMAIN_API.md §4 (Finding Lifecycle & submit_finding() Flow):
        1. **Logical ID Verification**: Generate logical_id if missing.
        2. **Evidence Storage**: Persist evidence records (dedup via INSERT OR IGNORE).
        3. **Finding Lookup**: Query database for existing finding by logical_id.
        4. **State Comparison**:
           - Content Unchanged → return existing finding (no new DB record).
           - Content Modified → new finding_id UUID, increment version.
           - New Finding → version 1 from __post_init__.
        5. **Persist** finding, link evidence via the finding_evidences
           junction table (MTKLAB-008), and update related hypotheses.

        Args:
            finding: The Finding to register.
            evidences: Optional list of Evidence objects supporting the finding.

        Returns:
            The Finding as stored, or the existing Finding if unchanged.
        """
        # 1. Verify/generate logical_id
        if not finding.logical_id:
            finding.logical_id = generate_logical_id(
                finding.experiment_id, str(finding.kind), finding.offset, finding.size
            )

        # 2. Store evidence and calculate confidence
        if evidences:
            for ev in evidences:
                self.db.store_evidence(ev)
                if ev.evidence_id not in finding.evidence_ids:
                    finding.evidence_ids.append(ev.evidence_id)
            finding.confidence = self._calculate_confidence(evidences)

        # 3. Lookup existing finding by logical_id
        existing = self.db.get_latest_finding_by_logical_id(finding.logical_id)

        # 4. Deduplication and versioning
        if existing:
            if self._is_finding_unchanged(existing, finding):
                # Content unchanged — return existing finding without new DB
                # record. Any newly-submitted evidence was still persisted
                # in step 2 above, so it must still be linked to the finding
                # actually being returned (existing.finding_id), or it would
                # be recorded in `evidences` but orphaned from
                # `finding_evidences` (MTKLAB-008).
                if finding.evidence_ids:
                    self.db.link_finding_evidences(existing.finding_id, finding.evidence_ids)
                return existing
            # Content modified — generate new finding_id and add version snapshot
            finding.finding_id = str(uuid.uuid4())
            # Inherit version history from existing finding for continuity
            finding.versions = list(existing.versions)
            finding.add_version("updated")
        else:
            # New finding — __post_init__ already created version 1 ("created")
            # Add submission snapshot to capture post-evidence confidence state
            finding.add_version("initial_submission")

        # 5. Store finding, link its evidence, and update hypotheses
        self.db.store_finding(finding)
        if finding.evidence_ids:
            self.db.link_finding_evidences(finding.finding_id, finding.evidence_ids)
        self._update_hypotheses(finding)

        return finding

    def _is_finding_unchanged(self, existing: Finding, incoming: Finding) -> bool:
        """Check if an existing finding is unchanged from the incoming one.

        Compares the four content fields (confidence, label, description,
        metadata) per DOMAIN_API.md §4.  If all match, the finding is
        considered identical and no new version is needed.

        Args:
            existing: The finding retrieved from the database.
            incoming: The finding currently being submitted.

        Returns:
            True if all compared fields match exactly.
        """
        return (
            existing.confidence == incoming.confidence
            and existing.label == incoming.label
            and existing.description == incoming.description
            and existing.metadata == incoming.metadata
        )

    def _get_latest_version_num(self, finding: Finding) -> int:
        """Extract the highest version number from a finding's version history.

        Args:
            finding: A Finding object with a populated ``versions`` list.

        Returns:
            The version number from the last entry in the versions list,
            or 1 if the list is empty or the last entry lacks a version key.
        """
        if finding.versions:
            return finding.versions[-1].get("version", 1)
        return 1

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