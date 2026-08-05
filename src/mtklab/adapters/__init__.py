"""MStar Adapters - zero-rewrite wrappers around mstar_analyzer modules."""

from .mstar_entropy import MStarEntropyAdapter, EntropyScanConfig
from .mstar_signatures import MStarSignaturesAdapter, MTK_PATTERNS
from .mstar_firmware_map import MStarFirmwareMapAdapter

__all__ = [
    "MStarEntropyAdapter",
    "EntropyScanConfig",
    "MStarSignaturesAdapter",
    "MTK_PATTERNS",
    "MStarFirmwareMapAdapter",
]