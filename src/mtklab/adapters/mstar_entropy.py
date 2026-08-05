"""MStar entropy adapter - wraps mstar_analyzer.entropy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel


try:
    from mstar_analyzer.entropy import (
        scan_entropy, EntropyPoint, shannon_entropy,
        classify_region, high_entropy_regions, sparkline
    )
    MSTAR_AVAILABLE = True
except ImportError:
    MSTAR_AVAILABLE = False
    # Stub types for type hints
    class EntropyPoint: pass


@dataclass
class EntropyScanConfig:
    window: int = 4096
    step: Optional[int] = None
    high_entropy_threshold: float = 7.2


class MStarEntropyAdapter:
    """Adapts MStar entropy module to Evidence Engine format."""
    
    def __init__(self, config: Optional[EntropyScanConfig] = None):
        if not MSTAR_AVAILABLE:
            raise RuntimeError("mstar_analyzer not available. Install the MStar analyzer package.")
        self.config = config or EntropyScanConfig()
    
    def scan(self, data: bytes, experiment_id: str) -> tuple[list[EntropyPoint], list[Evidence]]:
        """Run entropy scan and produce standardized evidence."""
        points = scan_entropy(data, self.config.window, self.config.step)
        evidences = []
        
        if not points:
            return points, evidences
        
        # Region transitions as evidence
        cur_class = classify_region(points[0].entropy)
        cur_start = points[0].offset
        
        for i in range(1, len(points)):
            cls = classify_region(points[i].entropy)
            if cls != cur_class:
                ev = Evidence(
                    evidence_id=str(uuid.uuid4()),
                    experiment_id=experiment_id,
                    evidence_type=EvidenceType.ENTROPY_BOUNDARY,
                    confidence=ConfidenceLevel.PROBABLE,
                    description=f"Entropy transition: {cur_class} → {cls}",
                    data={
                        "offset": points[i].offset,
                        "from_class": cur_class,
                        "to_class": cls,
                        "from_entropy": points[i-1].entropy,
                        "to_entropy": points[i].entropy,
                        "window_size": self.config.window,
                    },
                    source_offset=points[i].offset,
                    tags=["entropy_boundary", cur_class, cls]
                )
                evidences.append(ev)
                cur_class = cls
                cur_start = points[i].offset
        
        # High-entropy regions
        for start, end in high_entropy_regions(points, threshold=self.config.high_entropy_threshold):
            ev = Evidence(
                evidence_id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                evidence_type=EvidenceType.ENTROPY_BOUNDARY,
                confidence=ConfidenceLevel.CANDIDATE,
                description=f"High-entropy region (likely compressed/encrypted)",
                data={
                    "start": start,
                    "end": end,
                    "size": end - start,
                    "threshold": self.config.high_entropy_threshold,
                },
                source_offset=start,
                source_size=end - start,
                tags=["high_entropy_region"]
            )
            evidences.append(ev)
        
        return points, evidences
    
    def sparkline(self, points: list[EntropyPoint], width: int = 120) -> str:
        return sparkline(points, width=width)
    
    def classify_region(self, entropy: float) -> str:
        return classify_region(entropy)