"""Tests for exp04_text_header_parser.

The primary fixture uses the ACTUAL byte content observed on the real
Thundeal TD98 Pro upgrade_image.pkg during architecture review:

    # REE_OFFSET_START = 0x1000 #
    # REE_OFFSET_LEN = 0x5aeb0000 #

not the comma-separated "KEY=VALUE, KEY2=VALUE2" format originally guessed
from config/firmware.yaml's free-text description (config/firmware.yaml
is a prior hypothesis, not ground truth -- real bytes take precedence).
These tests double as a "framework discovers at least the documented known
structures" regression check for this specific structure (MTKLAB-013
direction), without needing the full real (multi-hundred-MB) firmware
file.
"""

import logging
import tempfile
import unittest
from pathlib import Path

from mtklab.core.experiment import ExperimentContext, ProgressReporter
from mtklab.core.evidence import ConfidenceLevel
from mtklab.experiments.exp04_text_header_parser.exp04_text_header_parser import (
    Exp04TextHeaderParser,
)


def _build_ota_with_text_header(path: Path, text: bytes, offset: int = 0x300, total_size: int = 0x400) -> None:
    buf = bytearray(max(total_size, offset + len(text)))
    buf[offset:offset + len(text)] = text
    path.write_bytes(bytes(buf))


class TestParseKeyValuePairs(unittest.TestCase):
    """Direct unit tests for the parsing helper."""

    def setUp(self):
        self.exp = Exp04TextHeaderParser()

    def test_parses_documented_real_header_exactly(self):
        pairs = self.exp._parse_key_value_pairs("REE_OFFSET_START=0x1000, REE_OFFSET_LEN=0x5AEB0000")
        self.assertEqual(pairs, {"REE_OFFSET_START": 0x1000, "REE_OFFSET_LEN": 0x5AEB0000})

    def test_parses_actual_real_firmware_format(self):
        """The ACTUAL byte content observed on the real TD98 Pro
        upgrade_image.pkg (not the comma-separated format originally
        assumed from config/firmware.yaml's free-text description) --
        confirmed during architecture review with real firmware bytes.
        Regression guard: this must never regress back to only supporting
        the originally-guessed format."""
        real_text = "# REE_OFFSET_START = 0x1000 #\n# REE_OFFSET_LEN = 0x5aeb0000 #"
        pairs = self.exp._parse_key_value_pairs(real_text)
        self.assertEqual(pairs, {"REE_OFFSET_START": 0x1000, "REE_OFFSET_LEN": 0x5AEB0000})

    def test_decimal_values_supported(self):
        pairs = self.exp._parse_key_value_pairs("COUNT=42")
        self.assertEqual(pairs, {"COUNT": 42})

    def test_malformed_segment_skipped_not_fatal(self):
        pairs = self.exp._parse_key_value_pairs("GOOD=0x1, not_a_pair, ALSO_GOOD=0x2, BAD=notanumber")
        self.assertEqual(pairs, {"GOOD": 1, "ALSO_GOOD": 2})

    def test_empty_string_returns_empty_dict(self):
        self.assertEqual(self.exp._parse_key_value_pairs(""), {})

    def test_whitespace_tolerant(self):
        pairs = self.exp._parse_key_value_pairs("  KEY  =  0x10  ,  KEY2=0x20  ")
        self.assertEqual(pairs, {"KEY": 0x10, "KEY2": 0x20})


class TestExp04TextHeaderParser(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.artifacts_dir = self.tmpdir / "artifacts"
        self.artifacts_dir.mkdir()

    def _make_ctx(self, firmware_path: Path) -> ExperimentContext:
        return ExperimentContext(
            firmware_path=firmware_path,
            ree_payload_path=self.tmpdir / "unused_ree_payload.bin",
            config={},
            evidence_db=None,
            artifacts_dir=self.artifacts_dir,
            shared_data={},
            progress=ProgressReporter(),
            logger=logging.getLogger("mtklab.test"),
        )

    def test_missing_ota_package_fails_cleanly(self):
        ctx = self._make_ctx(self.tmpdir / "does_not_exist.pkg")
        result = Exp04TextHeaderParser().run(ctx)
        self.assertEqual(result.status, "failed")

    def test_reads_from_firmware_path_not_ree_payload_path(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        _build_ota_with_text_header(ota_path, b"REE_OFFSET_START=0x1000, REE_OFFSET_LEN=0x5AEB0000")
        result = Exp04TextHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "success")

    def test_documented_header_matches_default_expected_hints(self):
        """The ACTUAL real text_header content (# KEY = VALUE # style,
        newline-separated), not the originally-guessed comma format."""
        ota_path = self.tmpdir / "upgrade_image.pkg"
        real_text = b"# REE_OFFSET_START = 0x1000 #\n# REE_OFFSET_LEN = 0x5aeb0000 #"
        _build_ota_with_text_header(ota_path, real_text)

        result = Exp04TextHeaderParser().run(self._make_ctx(ota_path))

        self.assertEqual(result.status, "success")
        finding = result.findings[0]
        self.assertEqual(finding.offset, 0x300)
        self.assertEqual(finding.confidence, ConfidenceLevel.PROBABLE)
        self.assertEqual(finding.metadata["mismatches"], [])
        self.assertEqual(
            finding.metadata["parsed_pairs"],
            {"REE_OFFSET_START": "0x1000", "REE_OFFSET_LEN": "0x5aeb0000"},
        )
        # 1 STRING_CLUSTER (raw text) + 2 CROSS_REFERENCE (one per key)
        self.assertEqual(len(result.evidences), 3)

    def test_mismatch_against_configured_hints_is_reported_not_fatal(self):
        """A firmware update changing REE_OFFSET_LEN must be surfaced as an
        informational mismatch, not treated as a failure -- the header was
        still successfully found and parsed."""
        ota_path = self.tmpdir / "upgrade_image.pkg"
        _build_ota_with_text_header(ota_path, b"REE_OFFSET_START=0x1000, REE_OFFSET_LEN=0x99999999")

        result = Exp04TextHeaderParser().run(self._make_ctx(ota_path))

        self.assertEqual(result.status, "partial")
        finding = result.findings[0]
        self.assertEqual(len(finding.metadata["mismatches"]), 1)
        self.assertIn("REE_OFFSET_LEN", finding.metadata["mismatches"][0])
        self.assertEqual(finding.confidence, ConfidenceLevel.CANDIDATE)

    def test_missing_expected_key_reported_as_mismatch(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        _build_ota_with_text_header(ota_path, b"REE_OFFSET_START=0x1000")  # LEN missing entirely

        result = Exp04TextHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        mismatches = result.findings[0].metadata["mismatches"]
        self.assertTrue(any("REE_OFFSET_LEN" in m and "not found" in m for m in mismatches))

    def test_non_ascii_or_garbage_region_does_not_crash(self):
        ota_path = self.tmpdir / "garbage.pkg"
        import os
        buf = bytearray(0x400)
        buf[0x300:0x400] = os.urandom(0x100)
        ota_path.write_bytes(bytes(buf))

        result = Exp04TextHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.findings), 1)  # still reports a low-confidence finding, not a crash

    def test_file_too_small_fails_cleanly(self):
        ota_path = self.tmpdir / "truncated.pkg"
        ota_path.write_bytes(b"\x00" * 0x100)  # smaller than header_offset(0x300)+header_size
        result = Exp04TextHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "failed")
        self.assertIn("too small", result.summary)

    def test_custom_header_offset_and_hints_are_respected(self):
        ota_path = self.tmpdir / "alt.pkg"
        _build_ota_with_text_header(ota_path, b"FOO=0x42", offset=0x800, total_size=0x900)

        exp = Exp04TextHeaderParser()
        exp.parameters = dict(exp.parameters, header_offset=0x800, expected_hints={"FOO": 0x42})
        result = exp.run(self._make_ctx(ota_path))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.findings[0].offset, 0x800)
        self.assertEqual(result.findings[0].metadata["mismatches"], [])


if __name__ == "__main__":
    unittest.main()
