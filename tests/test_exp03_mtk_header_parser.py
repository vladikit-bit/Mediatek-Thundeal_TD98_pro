"""Tests for exp03_mtk_header_parser (MTKLAB-013).

The synthetic fixture built here deliberately mirrors
config/firmware.yaml's known_structures section byte-for-byte (offsets,
sizes, and the magic/anchor values actually observed by manual hex
analysis of the real Thundeal TD98 Pro / MT5889 OTA image) so these tests
double as the "framework discovers at least the documented known
structures" regression check MTKLAB-013 asks for -- without needing the
real (multi-hundred-MB) firmware file, which is not available in this
environment.
"""

import logging
import os
import struct
import tempfile
import unittest
from pathlib import Path

from mtklab.core.experiment import ExperimentContext, ProgressReporter
from mtklab.core.evidence import ConfidenceLevel
from mtklab.experiments.exp03_mtk_header_parser.exp03_mtk_header_parser import (
    Exp03MtkHeaderParser,
)


def _build_synthetic_ota(path: Path, corrupt_magic: bool = False, truncate: bool = False) -> None:
    """Mirrors config/firmware.yaml known_structures:
    0x000 crypto_header (256B): high-entropy + zero padding
    0x100 padding (512B): zeros
    0x300 text_header (256B): REE_OFFSET_START=0x1000, REE_OFFSET_LEN=0x5AEB0000
    0x500 mtk_binary_header (512B): "MTK" + known anchor values (0x6009, 0x100000, 0x5AEB0000)
    """
    size = 0x300 if truncate else 0x1100
    buf = bytearray(size)
    buf[0x0:0x0 + min(160, size)] = os.urandom(min(160, size))

    if size > 0x300:
        text = b"REE_OFFSET_START=0x1000, REE_OFFSET_LEN=0x5AEB0000"
        buf[0x300:0x300 + len(text)] = text

    if size > 0x500:
        magic = b"XYZ" if corrupt_magic else b"MTK"
        buf[0x500:0x503] = magic
        buf[0x510:0x512] = struct.pack("<H", 0x6009)
        buf[0x520:0x524] = struct.pack("<I", 0x100000)
        buf[0x530:0x534] = struct.pack("<I", 0x5AEB0000)

    path.write_bytes(bytes(buf))


class TestExp03MtkHeaderParser(unittest.TestCase):
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
        result = Exp03MtkHeaderParser().run(ctx)
        self.assertEqual(result.status, "failed")
        self.assertIn("not found", result.summary)

    def test_reads_from_firmware_path_not_ree_payload_path(self):
        """Regression guard for the core design decision: the header lives
        in the OTA package, before the REE payload starts -- this must
        read ctx.firmware_path, never ctx.ree_payload_path."""
        ota_path = self.tmpdir / "upgrade_image.pkg"
        _build_synthetic_ota(ota_path)
        ctx = self._make_ctx(ota_path)
        # ree_payload_path intentionally points nowhere real (see _make_ctx);
        # if the experiment ever read from it by mistake, this would fail.
        result = Exp03MtkHeaderParser().run(ctx)
        self.assertEqual(result.status, "success")

    def test_documented_structure_fully_discovered(self):
        """The 'discovers at least the documented known structures' check:
        magic confirmed AND all 3 documented anchor values found at their
        correct absolute offsets."""
        ota_path = self.tmpdir / "upgrade_image.pkg"
        _build_synthetic_ota(ota_path)
        result = Exp03MtkHeaderParser().run(self._make_ctx(ota_path))

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.offset, 0x500)
        self.assertEqual(finding.size, 512)
        self.assertEqual(finding.confidence, ConfidenceLevel.PROBABLE)
        self.assertTrue(finding.metadata["magic_found"])
        self.assertEqual(len(finding.metadata["anchor_matches"]), 3)

        found_values = {m["value"] for m in finding.metadata["anchor_matches"]}
        self.assertEqual(found_values, {0x6009, 0x100000, 0x5AEB0000})

        ree_length_match = next(m for m in finding.metadata["anchor_matches"] if m["value"] == 0x5AEB0000)
        self.assertEqual(ree_length_match["absolute_offset"], 0x530)

    def test_evidence_matches_findings_count(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        _build_synthetic_ota(ota_path)
        result = Exp03MtkHeaderParser().run(self._make_ctx(ota_path))
        # 1 magic signature + 3 anchor matches
        self.assertEqual(len(result.evidences), 4)

    def test_missing_magic_reports_partial_not_crash(self):
        ota_path = self.tmpdir / "corrupt.pkg"
        _build_synthetic_ota(ota_path, corrupt_magic=True)
        result = Exp03MtkHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.findings[0].metadata["magic_found"])
        # Anchor values are still independently searched for and found,
        # even without the magic -- evidence is not all-or-nothing.
        self.assertEqual(len(result.findings[0].metadata["anchor_matches"]), 3)

    def test_file_too_small_fails_cleanly(self):
        ota_path = self.tmpdir / "truncated.pkg"
        _build_synthetic_ota(ota_path, truncate=True)  # only 0x300 bytes, header needs 0x500+512
        result = Exp03MtkHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "failed")
        self.assertIn("too small", result.summary)

    def test_no_anchor_values_and_no_magic_still_returns_partial_not_crash(self):
        ota_path = self.tmpdir / "unrelated.pkg"
        ota_path.write_bytes(os.urandom(0x1100))  # pure noise, vanishingly unlikely to collide
        result = Exp03MtkHeaderParser().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.findings), 1)  # still reports a (low-confidence) finding, not zero
        self.assertEqual(result.findings[0].confidence, ConfidenceLevel.CANDIDATE)

    def test_custom_header_offset_parameter_is_respected(self):
        """Non-default header_offset (e.g. a different device/layout) must
        actually be used, not hardcoded to 0x500."""
        ota_path = self.tmpdir / "alt_layout.pkg"
        buf = bytearray(0x2000)
        buf[0x1000:0x1003] = b"MTK"
        ota_path.write_bytes(bytes(buf))

        exp = Exp03MtkHeaderParser()
        exp.parameters = dict(exp.parameters, header_offset=0x1000, known_value_candidates=[])
        result = exp.run(self._make_ctx(ota_path))
        # No known_value_candidates configured -> magic alone isn't enough
        # for "success" (status requires magic AND >=2 anchors, matching
        # test_documented_structure_fully_discovered's stronger case), but
        # the custom offset itself must still be honored.
        self.assertEqual(result.status, "partial")
        self.assertTrue(result.findings[0].metadata["magic_found"])
        self.assertEqual(result.findings[0].offset, 0x1000)


if __name__ == "__main__":
    unittest.main()
