"""Exp03 MTK Header Parser - Parses the MediaTek binary header found by
manual hex analysis of the Thundeal TD98 Pro (MT5889) OTA package.

Unlike exp01/exp02 (generic, vendor-independent core experiments), this is
a deliberately MediaTek/TD98-specific module, in the spirit of the
project's own architecture: "vendor-specific modules should eventually
validate and refine hypotheses" -- device-specific offsets and expected
values belong here, not in the generic core.

Design note (epistemic honesty): only three fields inside the 512-byte
header have actually been confirmed by manual inspection (see
config/firmware.yaml known_structures) -- the magic signature and two
numeric values, one of which exactly matches the known REE payload length.
The full C-struct layout of the header has NOT been reverse engineered.
Rather than inventing a fake fixed-offset field layout, this experiment
SEARCHES the header for the known anchor values and records each match as
Evidence with its actual found offset. This is intentionally weaker than a
"parsed struct" but avoids fabricating field positions nobody has verified;
future work can narrow the layout down from the accumulated evidence.
"""

from mtklab.experiments import Experiment, ExperimentContext, ExperimentResult
from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind


class Exp03MtkHeaderParser(Experiment):
    """Locates and parses the MediaTek binary header via magic signature
    plus a search for known anchor field values, at a fixed offset in the
    OTA package (NOT the extracted REE payload -- the header sits before
    the REE payload starts, see config/firmware.yaml hints.ree_offset)."""

    experiment_id = "exp03_mtk_header_parser"
    display_name = "MTK Binary Header Parser"
    description = "Parses the MediaTek binary header in the OTA package via magic + known-value anchor search"
    version = "1.0.0"
    requires = []
    parameters = {
        # Defaults sourced from manual hex-editor analysis of the real
        # Thundeal TD98 Pro (MT5889) firmware -- see
        # config/firmware.yaml known_structures[mtk_binary_header] and
        # hints.mtk_header_offset. Both offset relative to ctx.firmware_path
        # (the OTA .pkg), not ctx.ree_payload_path.
        "header_offset": 0x500,
        "header_size": 512,
        "magic_bytes": b"MTK",
        # Known anchor values observed inside the header on the real image.
        # Searched for (little-endian) rather than assumed at a fixed
        # sub-offset, since the exact struct layout is not yet confirmed --
        # see module docstring.
        "known_value_candidates": [
            {
                "value": 0x6009,
                "bits": 16,
                "hypothesis": "possible partition type/version tag",
            },
            {
                "value": 0x100000,
                "bits": 32,
                "hypothesis": "possible load address or partition size (1 MiB)",
            },
            {
                "value": 0x5AEB0000,
                "bits": 32,
                "hypothesis": "REE payload length (matches config/firmware.yaml hints.ree_length)",
            },
        ],
    }

    def run(self, ctx: ExperimentContext) -> ExperimentResult:
        # Deliberately ctx.firmware_path (the OTA package), not
        # ctx.ree_payload_path: the header lives before the REE payload
        # begins (offset 0x500 vs. ree_offset 0x1000), so it is only
        # present in the outer .pkg file, not in the extracted payload.
        fw_path = ctx.firmware_path
        if not fw_path.exists():
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="failed",
                summary=f"OTA package not found at {fw_path}",
                errors=[f"File not found: {fw_path}"],
            )

        header_offset = self.parameters.get("header_offset", 0x500)
        header_size = self.parameters.get("header_size", 512)
        magic = self.parameters.get("magic_bytes", b"MTK")

        file_size = fw_path.stat().st_size
        if file_size < header_offset + header_size:
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="failed",
                summary=(
                    f"OTA package is {file_size:,} bytes, too small to contain a header "
                    f"at 0x{header_offset:X} + {header_size} bytes"
                ),
                errors=[f"File too small: {file_size} < {header_offset + header_size}"],
            )

        with fw_path.open("rb") as f:
            f.seek(header_offset)
            header = f.read(header_size)

        findings = []
        evidences = []

        # 1. Magic signature check.
        has_magic = header.startswith(magic)
        if has_magic:
            evidences.append(Evidence(
                experiment_id=self.experiment_id,
                evidence_type=EvidenceType.SIGNATURE_MATCH,
                confidence=ConfidenceLevel.VERIFIED,
                description=f"Magic signature {magic!r} found at 0x{header_offset:X}",
                data={"magic": magic.decode("ascii", errors="replace"), "offset": header_offset},
                source_offset=header_offset,
                source_size=len(magic),
                tags=["mtk_header", "magic"],
            ))
        else:
            ctx.logger.warning(
                f"Expected magic {magic!r} at 0x{header_offset:X} in {fw_path.name}, "
                f"found {header[:len(magic)]!r} instead -- this OTA image may use a "
                "different header offset/format than the TD98 Pro defaults."
            )

        # 2. Search for known anchor values anywhere in the header (not
        # assumed at a fixed sub-offset -- see module docstring). Every
        # occurrence is recorded, since a value could legitimately repeat.
        anchor_matches = []
        for candidate in self.parameters.get("known_value_candidates", []):
            value = candidate["value"]
            bits = candidate["bits"]
            needle = value.to_bytes(bits // 8, "little")
            pos = 0
            while True:
                idx = header.find(needle, pos)
                if idx == -1:
                    break
                field_offset = header_offset + idx
                anchor_matches.append({
                    "value": value,
                    "bits": bits,
                    "offset_in_header": idx,
                    "absolute_offset": field_offset,
                    "hypothesis": candidate["hypothesis"],
                })
                evidences.append(Evidence(
                    experiment_id=self.experiment_id,
                    evidence_type=EvidenceType.OFFSET_REFERENCE,
                    confidence=ConfidenceLevel.PROBABLE,
                    description=(
                        f"Candidate field 0x{value:X} ({candidate['hypothesis']}) at "
                        f"header+0x{idx:X} (absolute 0x{field_offset:X})"
                    ),
                    data={
                        "value": value,
                        "bits": bits,
                        "offset_in_header": idx,
                        "absolute_offset": field_offset,
                        "hypothesis": candidate["hypothesis"],
                    },
                    source_offset=field_offset,
                    source_size=bits // 8,
                    tags=["mtk_header", "candidate_field"],
                ))
                pos = idx + 1

        # 3. One Finding for the header region as a whole. Confidence
        # reflects how much corroborating evidence was actually found, not
        # an assumption that the (unverified) full layout is correct.
        if has_magic and len(anchor_matches) >= 2:
            confidence = ConfidenceLevel.PROBABLE
        else:
            confidence = ConfidenceLevel.CANDIDATE

        findings.append(Finding(
            experiment_id=self.experiment_id,
            kind=FindingKind.HEADER,
            offset=header_offset,
            size=header_size,
            confidence=confidence,
            label="MTK Binary Header",
            description=(
                f"MediaTek binary header at 0x{header_offset:X}"
                + (" (magic confirmed)" if has_magic else " (magic NOT found)")
                + f", {len(anchor_matches)} candidate field(s) matched"
            ),
            metadata={
                "magic_found": has_magic,
                "magic_bytes": magic.decode("ascii", errors="replace"),
                "anchor_matches": anchor_matches,
                "header_hex_preview": header[:64].hex(),
            },
        ))

        if has_magic and len(anchor_matches) >= 2:
            status = "success"
        else:
            status = "partial"

        return ExperimentResult(
            experiment_id=self.experiment_id,
            status=status,
            summary=(
                f"MTK header {'confirmed' if has_magic else 'not confirmed'} at "
                f"0x{header_offset:X}: magic={has_magic}, "
                f"{len(anchor_matches)}/{len(self.parameters.get('known_value_candidates', []))} "
                f"known anchor value(s) found"
            ),
            findings=findings,
            evidences=evidences,
            metadata={
                "header_offset": header_offset,
                "header_size": header_size,
                "magic_found": has_magic,
                "anchor_match_count": len(anchor_matches),
            },
        )
