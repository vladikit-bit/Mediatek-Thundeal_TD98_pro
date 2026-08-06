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

    @dataclass
    class EntropyPoint:
        offset: int
        entropy: float

    def shannon_entropy(data: bytes) -> float:
        import math
        from collections import Counter
        if not data:
            return 0.0
        length = len(data)
        counts = Counter(data)
        entropy = 0.0
        for count in counts.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    def classify_region(entropy: float) -> str:
        if entropy < 1.0:
            return "zero/padding"
        elif entropy < 5.0:
            return "low_entropy/code"
        elif entropy < 7.2:
            return "medium_entropy/data"
        else:
            return "high_entropy/compressed_or_encrypted"

    def scan_entropy(data: bytes, window: int = 4096, step: Optional[int] = None) -> list[EntropyPoint]:
        step = step or window
        points = []
        for offset in range(0, len(data), step):
            chunk = data[offset:offset + window]
            if not chunk:
                break
            e = shannon_entropy(chunk)
            points.append(EntropyPoint(offset=offset, entropy=e))
        return points

    def high_entropy_regions(points: list[EntropyPoint], threshold: float = 7.2) -> list[tuple[int, int]]:
        regions = []
        in_region = False
        start = 0
        end = 0
        for p in points:
            if p.entropy >= threshold:
                if not in_region:
                    in_region = True
                    start = p.offset
                end = p.offset + 4096
            else:
                if in_region:
                    regions.append((start, end))
                    in_region = False
        if in_region:
            regions.append((start, end))
        return regions

    def sparkline(points: list[EntropyPoint], width: int = 120) -> str:
        if not points:
            return ""
        ticks = " ▂▃▄▅▆▇█"
        step = max(1, len(points) // width)
        sampled = [points[i].entropy for i in range(0, len(points), step)][:width]
        res = []
        for val in sampled:
            idx = min(7, max(0, int((val / 8.0) * 8)))
            res.append(ticks[idx])
        return "".join(res)


@dataclass
class EntropyScanConfig:
    window: int = 4096
    step: Optional[int] = None
    high_entropy_threshold: float = 7.2


class MStarEntropyAdapter:
    """Adapts MStar entropy module to Evidence Engine format."""
    
    def __init__(self, config: Optional[EntropyScanConfig] = None):
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