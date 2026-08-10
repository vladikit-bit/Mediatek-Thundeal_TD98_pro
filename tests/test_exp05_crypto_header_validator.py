"""Tests for exp05_crypto_header_validator.

Includes a dedicated regression test for a real bug found during
development: the naive default of reusing exp01's high_entropy_threshold
(7.2, calibrated for 4096-byte scan windows) made this experiment fail on
EVERY genuinely random 160-byte signature sample (verified empirically:
30/30 trials measured below 7.2, since a 160-byte sample cannot reach
close to the 8.0 bits/byte theoretical maximum). Fixed via a size-aware
default threshold (_min_entropy_for_random_sample); this file's tests
guard against that regression coming back.
"""

import logging
import os
import tempfile
import unittest
from pathlib import Path

from mtklab.core.experiment import ExperimentContext, ProgressReporter
from mtklab.core.evidence import ConfidenceLevel
from mtklab.experiments.exp05_crypto_header_validator.exp05_crypto_header_validator import (
    Exp05CryptoHeaderValidator,
    _min_entropy_for_random_sample,
)


class TestMinEntropyForRandomSample(unittest.TestCase):
    def test_scales_with_sample_size(self):
        self.assertLess(_min_entropy_for_random_sample(32), _min_entropy_for_random_sample(4096))

    def test_never_exceeds_8_bits(self):
        self.assertLessEqual(_min_entropy_for_random_sample(1_000_000), 8.0)

    def test_handles_tiny_sample_without_math_domain_error(self):
        # log2(1) == 0, log2(0) is undefined -- must not raise either way.
        _min_entropy_for_random_sample(1)
        _min_entropy_for_random_sample(0)


class TestRandomSampleActuallyPassesDefaultThreshold(unittest.TestCase):
    """Statistical regression guard: this is the exact bug found during
    development (see module docstring). Runs multiple trials since a
    single lucky/unlucky RNG draw wouldn't prove the fix is real."""

    def test_160_byte_random_samples_pass_default_threshold(self):
        threshold = _min_entropy_for_random_sample(160)
        from mtklab.adapters.mstar_entropy import shannon_entropy
        failures = 0
        for _ in range(25):
            e = shannon_entropy(os.urandom(160))
            if e < threshold:
                failures += 1
        self.assertEqual(failures, 0, f"{failures}/25 random samples fell below the default threshold")

    def test_old_fixed_7_2_threshold_would_have_failed(self):
        """Documents WHY the fix was needed: confirms the old hardcoded
        7.2 default (borrowed from exp01) is unreachable for a 160-byte
        sample, so a regression back to a fixed 7.2 would be caught by
        the test above failing, not silently reintroduced."""
        from mtklab.adapters.mstar_entropy import shannon_entropy
        entropies = [shannon_entropy(os.urandom(160)) for _ in range(25)]
        self.assertTrue(all(e < 7.2 for e in entropies))


class TestExp05CryptoHeaderValidator(unittest.TestCase):
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

    def _build_ota(self, path: Path, signature: bytes = None, corrupt_zero_pad: bool = False,
                    corrupt_padding: bool = False, total_size: int = 0x400) -> None:
        buf = bytearray(total_size)
        sig = signature if signature is not None else os.urandom(160)
        buf[0x0:len(sig)] = sig
        if corrupt_zero_pad:
            buf[0xA0:0xA0 + 10] = os.urandom(10)  # inject noise into the zero-fill region
        if corrupt_padding:
            buf[0x150:0x160] = os.urandom(16)  # inject noise into the 0x100-0x300 padding region
        path.write_bytes(bytes(buf))

    def test_missing_ota_package_fails_cleanly(self):
        ctx = self._make_ctx(self.tmpdir / "does_not_exist.pkg")
        result = Exp05CryptoHeaderValidator().run(ctx)
        self.assertEqual(result.status, "failed")

    def test_reads_from_firmware_path_not_ree_payload_path(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        self._build_ota(ota_path)
        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "success")

    def test_documented_structure_passes_all_checks(self):
        """Random signature + zero-fill + zero padding -- exactly the
        documented real structure -- must report success with PROBABLE
        confidence on both findings, not a false negative."""
        ota_path = self.tmpdir / "upgrade_image.pkg"
        self._build_ota(ota_path)

        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.findings), 2)
        crypto_finding, padding_finding = result.findings
        self.assertEqual(crypto_finding.offset, 0x0)
        self.assertEqual(crypto_finding.size, 256)
        self.assertEqual(crypto_finding.confidence, ConfidenceLevel.PROBABLE)
        self.assertTrue(crypto_finding.metadata["signature_high_entropy"])
        self.assertTrue(crypto_finding.metadata["zero_pad_is_zero"])

        self.assertEqual(padding_finding.offset, 0x100)
        self.assertEqual(padding_finding.size, 512)
        self.assertTrue(padding_finding.metadata["is_zero"])

    def test_low_entropy_signature_reported_not_fatal(self):
        """An all-zero 'signature' region (clearly not a real signature)
        must be reported as a mismatch, not crash, and not silently pass."""
        ota_path = self.tmpdir / "upgrade_image.pkg"
        self._build_ota(ota_path, signature=b"\x00" * 160)

        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.findings[0].metadata["signature_high_entropy"])

    def test_corrupted_zero_fill_detected(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        self._build_ota(ota_path, corrupt_zero_pad=True)

        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.findings[0].metadata["zero_pad_is_zero"])
        self.assertLess(result.findings[0].metadata["zero_pad_ratio"], 1.0)

    def test_corrupted_padding_region_detected(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        self._build_ota(ota_path, corrupt_padding=True)

        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.findings[1].metadata["is_zero"])
        self.assertLess(result.findings[1].metadata["zero_ratio"], 1.0)

    def test_file_too_small_fails_cleanly(self):
        ota_path = self.tmpdir / "truncated.pkg"
        ota_path.write_bytes(b"\x00" * 0x50)
        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))
        self.assertEqual(result.status, "failed")
        self.assertIn("too small", result.summary)

    def test_evidence_count_matches_three_checks(self):
        ota_path = self.tmpdir / "upgrade_image.pkg"
        self._build_ota(ota_path)
        result = Exp05CryptoHeaderValidator().run(self._make_ctx(ota_path))
        # signature entropy + zero-fill + padding-region = 3 evidence items
        self.assertEqual(len(result.evidences), 3)

    def test_custom_offsets_and_explicit_threshold_respected(self):
        ota_path = self.tmpdir / "alt.pkg"
        buf = bytearray(0x1000)
        buf[0x800:0x820] = os.urandom(32)  # 32-byte "signature" at an alt offset
        ota_path.write_bytes(bytes(buf))

        exp = Exp05CryptoHeaderValidator()
        exp.parameters = dict(
            exp.parameters,
            crypto_header_offset=0x800,
            crypto_header_signature_size=32,
            crypto_header_zero_padding_size=0,
            padding_region_offset=0x900,
            padding_region_size=16,
            high_entropy_threshold=1.0,  # explicit override should be honored, not auto-computed
        )
        result = exp.run(self._make_ctx(ota_path))
        self.assertEqual(result.findings[0].offset, 0x800)
        self.assertEqual(result.findings[0].metadata["entropy_threshold"], 1.0)


if __name__ == "__main__":
    unittest.main()
