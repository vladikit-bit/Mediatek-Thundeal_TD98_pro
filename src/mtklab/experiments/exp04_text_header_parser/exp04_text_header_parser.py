"""Exp04 Text Header Parser - Parses the human-readable ASCII "KEY=VALUE"
header found by manual hex analysis of the Thundeal TD98 Pro (MT5889) OTA
package at offset 0x300 (see config/firmware.yaml known_structures ->
text_header: "REE_OFFSET_START=0x1000, REE_OFFSET_LEN=0x5AEB0000").

Unlike exp01/exp02 (generic core), this is a deliberately TD98/MT5889-
specific module, same rationale as exp03: vendor-specific offsets and
expected values belong in vendor-specific modules, not the generic core.

Why this experiment exists beyond exp03: the firmware is, at this offset,
self-describing -- it declares its OWN REE payload location and length in
plain ASCII, rather than requiring that information to only ever come from
manually-maintained config. This experiment parses that declaration
generically (any "KEY=VALUE, KEY2=VALUE2" text, not just the two keys seen
so far) and cross-checks it against the values this project's config
currently assumes, catching drift between what a human configured and what
the firmware itself actually states (e.g. after a firmware update changes
REE_OFFSET_LEN, or a config typo).
"""

from mtklab.experiments import Experiment, ExperimentContext, ExperimentResult
from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind
import re


class Exp04TextHeaderParser(Experiment):
    """Locates and parses the ASCII KEY=VALUE text header, cross-checking
    parsed values against this device's expected hints (config/firmware.yaml)."""

    experiment_id = "exp04_text_header_parser"
    display_name = "Text Header Parser"
    description = "Parses the ASCII KEY=VALUE header and cross-checks it against configured hints"
    version = "1.0.0"
    requires = []
    parameters = {
        # Defaults sourced from manual hex-editor analysis of the real
        # Thundeal TD98 Pro (MT5889) firmware -- see
        # config/firmware.yaml known_structures[text_header] and
        # hints.text_header_offset. Offset relative to ctx.firmware_path
        # (the OTA .pkg), not ctx.ree_payload_path -- same reasoning as
        # exp03: this header sits before the REE payload begins.
        "header_offset": 0x300,
        "header_size": 256,
        # Keys this device's firmware is known to declare at this offset,
        # and the values seen on the real image. Used only to cross-check
        # what gets parsed -- parsing itself does not require knowing the
        # key names in advance (see _parse_key_value_pairs).
        "expected_hints": {
            "REE_OFFSET_START": 0x1000,
            "REE_OFFSET_LEN": 0x5AEB0000,
        },
    }

    def run(self, ctx: ExperimentContext) -> ExperimentResult:
        # Deliberately ctx.firmware_path (the OTA package), not
        # ctx.ree_payload_path -- see module docstring / exp03.
        fw_path = ctx.firmware_path
        if not fw_path.exists():
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="failed",
                summary=f"OTA package not found at {fw_path}",
                errors=[f"File not found: {fw_path}"],
            )

        header_offset = self.parameters.get("header_offset", 0x300)
        header_size = self.parameters.get("header_size", 256)

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
            raw = f.read(header_size)

        # Text header is NUL-padded ASCII; strip trailing NULs before
        # decoding. errors="replace" keeps this robust against a region
        # that turns out not to be ASCII text at all (e.g. wrong offset on
        # a different device) rather than raising UnicodeDecodeError.
        text = raw.rstrip(b"\x00").decode("ascii", errors="replace")
        pairs = self._parse_key_value_pairs(text)

        findings = []
        evidences = []

        if text:
            evidences.append(Evidence(
                experiment_id=self.experiment_id,
                evidence_type=EvidenceType.STRING_CLUSTER,
                confidence=ConfidenceLevel.VERIFIED if pairs else ConfidenceLevel.CANDIDATE,
                description=f"ASCII text found at 0x{header_offset:X}: {text!r}",
                data={"text": text, "offset": header_offset},
                source_offset=header_offset,
                source_size=len(raw.rstrip(b"\x00")),
                tags=["text_header", "ascii"],
            ))

        for key, value in pairs.items():
            evidences.append(Evidence(
                experiment_id=self.experiment_id,
                evidence_type=EvidenceType.CROSS_REFERENCE,
                confidence=ConfidenceLevel.PROBABLE,
                description=f"{key}=0x{value:X} declared in text header at 0x{header_offset:X}",
                data={"key": key, "value": value},
                source_offset=header_offset,
                source_size=len(raw.rstrip(b"\x00")),
                tags=["text_header", "declared_value"],
            ))

        # Cross-check parsed values against this device's expected hints.
        # A mismatch is informational, not necessarily an error -- a
        # firmware update could legitimately change these -- so it is
        # surfaced in metadata for a human to judge, not treated as failure.
        mismatches = []
        expected_hints = self.parameters.get("expected_hints", {})
        for key, expected_value in expected_hints.items():
            if key not in pairs:
                mismatches.append(f"{key}: expected but not found in header")
            elif pairs[key] != expected_value:
                mismatches.append(
                    f"{key}: config expects 0x{expected_value:X}, header declares 0x{pairs[key]:X}"
                )

        if pairs and expected_hints and not mismatches:
            confidence = ConfidenceLevel.PROBABLE
        else:
            confidence = ConfidenceLevel.CANDIDATE

        findings.append(Finding(
            experiment_id=self.experiment_id,
            kind=FindingKind.HEADER,
            offset=header_offset,
            size=header_size,
            confidence=confidence,
            label="Text Header (KEY=VALUE)",
            description=(
                f"ASCII KEY=VALUE header at 0x{header_offset:X}: {len(pairs)} pair(s) parsed"
                + (f", {len(mismatches)} mismatch(es) vs. configured hints" if mismatches else "")
            ),
            evidence_ids=[e.evidence_id for e in evidences],
            metadata={
                "raw_text": text,
                "parsed_pairs": {k: hex(v) for k, v in pairs.items()},
                "mismatches": mismatches,
            },
        ))

        if pairs and not mismatches:
            status = "success"
        else:
            status = "partial"

        return ExperimentResult(
            experiment_id=self.experiment_id,
            status=status,
            summary=(
                f"Text header at 0x{header_offset:X}: {len(pairs)} key-value pair(s) parsed"
                + (f", {len(mismatches)} mismatch(es)" if mismatches else ", all hints match" if pairs and expected_hints else "")
            ),
            findings=findings,
            evidences=evidences,
            metadata={
                "header_offset": header_offset,
                "header_size": header_size,
                "pairs_found": len(pairs),
                "mismatch_count": len(mismatches),
            },
        )

    def _parse_key_value_pairs(self, text: str) -> dict[str, int]:
        """Parse "KEY = VALUE" declarations found anywhere in the text.

        IMPORTANT (found during real-firmware review): the original
        version of this parser assumed a specific delimiter style
        ("KEY=VALUE, KEY2=VALUE2", comma-separated, no spaces around "=")
        based on the wording in config/firmware.yaml. The real OTA image
        instead contains:

            # REE_OFFSET_START = 0x1000 #
            # REE_OFFSET_LEN = 0x5aeb0000 #

        i.e. spaces around "=", each declaration wrapped in "#", and
        (presumably) newline-separated rather than comma-separated. Rather
        than hardcoding this one now-observed format either -- which would
        just be trading one unverified assumption for another, and the
        exact separator between declarations still isn't confirmed byte-
        for-byte -- this searches for the one thing common to both the
        originally-assumed format and the real one: a bare "KEY = VALUE"
        token, regardless of surrounding punctuation or whitespace style.
        This is a strict generalization (a superset of both), not a new
        guess about formatting.
        """
        pairs: dict[str, int] = {}
        for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(0[xX][0-9A-Fa-f]+|\d+)", text):
            key, value_str = match.group(1), match.group(2)
            try:
                pairs[key] = int(value_str, 0)
            except ValueError:
                continue
        return pairs
