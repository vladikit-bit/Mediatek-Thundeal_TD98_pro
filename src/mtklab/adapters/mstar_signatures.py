"""MStar signatures adapter - wraps mstar_analyzer.signatures."""

from __future__ import annotations

import uuid
from typing import Optional

from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel


try:
    from mstar_analyzer.signatures import (
        scan_all, DEFAULT_SCANNERS, MagicScanner,
        AsciiMarkerScanner, LzmaHeuristicScanner, ZlibHeuristicScanner, Jffs2Scanner,
        iter_find, Finding as MStarFinding
    )
    MSTAR_AVAILABLE = True
except ImportError:
    MSTAR_AVAILABLE = False


# MT5889-specific additional patterns
MTK_PATTERNS = [
    (b"MTK", "MTK marker"),
    (b"MStar", "MStar marker"),
    (b"MSTAR", "MSTAR marker"),
    (b"REE", "REE marker"),
    (b"TEE", "TEE marker"),
    (b"TRUSTZONE", "TrustZone marker"),
    (b"MBoot", "MBoot marker"),
    (b"MBOOT", "MBOOT marker"),
    (b"eCos", "eCos marker"),
    (b"ECOS", "ECOS marker"),
    (b"Android", "Android marker"),
    (b"ANDROID", "ANDROID marker"),
    (b"Linux", "Linux marker"),
    (b"LINUX", "LINUX marker"),
    (b"U-Boot", "U-Boot marker"),
    (b"U-BOOT", "U-BOOT marker"),
    (b"bootloader", "bootloader marker"),
    (b"BOOTLOADER", "BOOTLOADER marker"),
]


class MStarSignaturesAdapter:
    """Adapts MStar signature scanners to Evidence Engine format."""
    
    def __init__(self, custom_scanners: list = None):
        if not MSTAR_AVAILABLE:
            raise RuntimeError("mstar_analyzer not available. Install the MStar analyzer package.")
        self.scanners = DEFAULT_SCANNERS + (custom_scanners or [])
    
    def scan(self, data: bytes, experiment_id: str) -> list[Evidence]:
        """Run signature scan and produce standardized evidence."""
        if not MSTAR_AVAILABLE:
            return []
        
        findings = scan_all(data, self.scanners)
        evidences = []
        
        for f in findings:
            # Map MStar finding confidence to our levels
            conf_map = {
                "high": ConfidenceLevel.PROBABLE,
                "medium": ConfidenceLevel.CANDIDATE,
                "low": ConfidenceLevel.CANDIDATE,
            }
            
            ev = Evidence(
                evidence_id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                evidence_type=EvidenceType.SIGNATURE_MATCH,
                confidence=conf_map.get(f.confidence, ConfidenceLevel.CANDIDATE),
                description=f"{f.name}: {f.detail}" if f.detail else f.name,
                data={
                    "scanner": f.name.split(":")[0] if ":" in f.name else "magic",
                    "pattern": f.name,
                    "detail": f.detail,
                },
                source_offset=f.offset,
                tags=[f.name.lower().replace(" ", "_").replace("-", "_")]
            )
            evidences.append(ev)
        
        # Add MTK pattern scan
        for pattern, label in MTK_PATTERNS:
            for offset in iter_find(data, pattern):
                ev = Evidence(
                    evidence_id=str(uuid.uuid4()),
                    experiment_id=experiment_id,
                    evidence_type=EvidenceType.SIGNATURE_MATCH,
                    confidence=ConfidenceLevel.CANDIDATE,
                    description=f"MTK pattern: {label}",
                    data={"pattern": pattern.hex(), "label": label},
                    source_offset=offset,
                    source_size=len(pattern),
                    tags=["mtk_pattern", label.lower().replace(" ", "_")]
                )
                evidences.append(ev)
        
        return evidences
    
    def scan_single(self, data: bytes, experiment_id: str, scanner_name: str) -> list[Evidence]:
        """Run a single named scanner."""
        scanner_map = {
            "magic": MagicScanner(),
            "ascii": AsciiMarkerScanner(),
            "lzma": LzmaHeuristicScanner(),
            "zlib": ZlibHeuristicScanner(),
            "jffs2": Jffs2Scanner(),
        }
        scanner = scanner_map.get(scanner_name)
        if not scanner:
            return []
        
        findings = scanner.scan(data)
        evidences = []
        for f in findings:
            conf_map = {"high": ConfidenceLevel.PROBABLE, "medium": ConfidenceLevel.CANDIDATE, "low": ConfidenceLevel.CANDIDATE}
            ev = Evidence(
                evidence_id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                evidence_type=EvidenceType.SIGNATURE_MATCH,
                confidence=conf_map.get(f.confidence, ConfidenceLevel.CANDIDATE),
                description=f"{f.name}: {f.detail}" if f.detail else f.name,
                data={"scanner": scanner_name, "pattern": f.name, "detail": f.detail},
                source_offset=f.offset,
                tags=[scanner_name, f.name.lower().replace(" ", "_")]
            )
            evidences.append(ev)
        return evidences