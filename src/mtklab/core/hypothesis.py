"""Hypothesis tracking for conflicting evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .evidence import ConfidenceLevel


class HypothesisStatus(Enum):
    """Status of a hypothesis."""

    PROPOSED = "proposed"  # Initial hypothesis
    SUPPORTED = "supported"  # Evidence favors it
    CONTESTED = "contested"  # Conflicting evidence exists
    REFUTED = "refuted"  # Evidence against it
    ACCEPTED = "accepted"  # Consensus reached

    def __str__(self) -> str:
        return self.value


@dataclass
class Hypothesis:
    """
    Tracks competing hypotheses about a region/object.

    Example:
        Hypothesis A: "Region at 0x14EBA6FC is eCos RTOS image"
          Supporting: Binwalk eCos signature, "eCos" string
          Contradicting: MBoot strings (MBOT-), executable layout
          Status: CONTESTED

        Hypothesis B: "Region at 0x14EBA6FC is MBoot environment block"
          Supporting: MBOT- marker, MBoot env block structure validated
          Status: SUPPORTED
    """

    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject_offset: int = 0
    subject_size: int | None = None
    claim: str = ""  # e.g., "This region is eCos RTOS image"
    alternative_claims: list[str] = field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.PROPOSED

    # Evidence for/against (store finding_ids or evidence_ids)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)

    # Resolution
    resolved_claim: str | None = None
    resolution_reason: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.CANDIDATE

    # Versioned history
    versions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.versions:
            self.versions.append(self._create_version_snapshot("proposed"))

    def _create_version_snapshot(self, reason: str) -> dict[str, Any]:
        return {
            "version": len(self.versions) + 1,
            "status": self.status.value,
            "claim": self.claim,
            "supporting_count": len(self.supporting_evidence),
            "contradicting_count": len(self.contradicting_evidence),
            "confidence": self.confidence.name,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def add_supporting(self, evidence_id: str):
        """Add supporting evidence."""
        if evidence_id not in self.supporting_evidence:
            self.supporting_evidence.append(evidence_id)
            self._recalculate_status()

    def add_contradicting(self, evidence_id: str):
        """Add contradicting evidence."""
        if evidence_id not in self.contradicting_evidence:
            self.contradicting_evidence.append(evidence_id)
            self._recalculate_status()

    def _recalculate_status(self):
        """Recalculate status based on evidence balance."""
        s = len(self.supporting_evidence)
        c = len(self.contradicting_evidence)

        if c > s:
            self.status = HypothesisStatus.REFUTED
        elif c > 0:
            self.status = HypothesisStatus.CONTESTED
        elif s >= 2:
            self.status = HypothesisStatus.SUPPORTED
        else:
            self.status = HypothesisStatus.PROPOSED

        # Upgrade confidence based on evidence
        if s >= 3:
            self.confidence = ConfidenceLevel.VERIFIED
        elif s >= 2:
            self.confidence = ConfidenceLevel.PROBABLE
        else:
            self.confidence = ConfidenceLevel.CANDIDATE

        self.versions.append(self._create_version_snapshot("evidence_update"))

    def resolve(self, claim: str, reason: str):
        """Manually resolve the hypothesis."""
        self.resolved_claim = claim
        self.resolution_reason = reason
        self.status = HypothesisStatus.ACCEPTED
        self.claim = claim
        self.versions.append(self._create_version_snapshot(f"resolved: {reason}"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "subject_offset": self.subject_offset,
            "subject_size": self.subject_size,
            "claim": self.claim,
            "alternative_claims": self.alternative_claims,
            "status": self.status.value,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "resolved_claim": self.resolved_claim,
            "resolution_reason": self.resolution_reason,
            "confidence": self.confidence.name,
            "versions": self.versions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Hypothesis":
        h = cls(
            hypothesis_id=d["hypothesis_id"],
            subject_offset=d["subject_offset"],
            subject_size=d.get("subject_size"),
            claim=d["claim"],
            alternative_claims=d.get("alternative_claims", []),
            status=HypothesisStatus(d["status"]),
            supporting_evidence=d.get("supporting_evidence", []),
            contradicting_evidence=d.get("contradicting_evidence", []),
            resolved_claim=d.get("resolved_claim"),
            resolution_reason=d.get("resolution_reason", ""),
            confidence=ConfidenceLevel[d["confidence"]],
        )
        h.versions = d.get("versions", [])
        return h