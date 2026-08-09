"""MStar firmware_map adapter - wraps mstar_analyzer.firmware_map."""

from __future__ import annotations

from typing import Optional

from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel


try:
    from mstar_analyzer.firmware_map import build_firmware_map, FirmwareMap, MapEntry
    from mstar_analyzer.entropy import EntropyPoint
    MSTAR_AVAILABLE = True
except ImportError:
    MSTAR_AVAILABLE = False
    class FirmwareMap: pass
    class MapEntry: pass


class MStarFirmwareMapAdapter:
    """Produces unified firmware map as evidence."""
    
    def __init__(self, entropy_window: int = 1024, lzma_threshold: float = 7.0):
        if not MSTAR_AVAILABLE:
            raise RuntimeError("mstar_analyzer not available. Install the MStar analyzer package.")
        self.entropy_window = entropy_window
        self.lzma_threshold = lzma_threshold
    
    def build_map(self, data: bytes, experiment_id: str) -> tuple[FirmwareMap, list[Evidence]]:
        fw_map = build_firmware_map(
            data,
            entropy_window=self.entropy_window,
            lzma_confidence_threshold=self.lzma_threshold
        )
        evidences = []
        
        for entry in fw_map.entries:
            ev_type = self._map_kind_to_type(entry.kind)
            
            ev = Evidence(
                experiment_id=experiment_id,
                evidence_type=ev_type,
                confidence=ConfidenceLevel.PROBABLE if entry.confidence == "high" else ConfidenceLevel.CANDIDATE,
                description=f"{entry.kind} at 0x{entry.offset:08X}: {entry.detail}",
                data={
                    "kind": entry.kind,
                    "detail": entry.detail,
                    "original_confidence": entry.confidence,
                },
                source_offset=entry.offset,
                tags=[entry.kind.lower().replace(" ", "_").replace("-", "_")]
            )
            evidences.append(ev)
        
        return fw_map, evidences
    
    def _map_kind_to_type(self, kind: str) -> EvidenceType:
        kind_lower = kind.lower()
        if "region:" in kind_lower:
            return EvidenceType.ENTROPY_BOUNDARY
        if "crc" in kind_lower:
            return EvidenceType.CRC_VALIDATION
        if "jffs2" in kind_lower:
            return EvidenceType.STRUCTURAL_PATTERN
        if "lzma" in kind_lower or "zlib" in kind_lower or "gzip" in kind_lower:
            return EvidenceType.SIGNATURE_MATCH
        return EvidenceType.SIGNATURE_MATCH
    
    def get_sparkline(self, fw_map: FirmwareMap, width: int = 120) -> str:
        return fw_map.sparkline(width=width)
    
    def get_table(self, fw_map: FirmwareMap, exclude_kinds: set = None) -> str:
        return fw_map.as_table(exclude_kinds=exclude_kinds or frozenset())