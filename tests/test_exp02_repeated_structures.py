"""Tests for the scalable rewrite of exp02_repeated_structures.

Background: the original implementation analyzed a candidate region with
`for pos in range(record_size): for i in range(max_records): ...`, touching
every byte of the region once per candidate record_size via per-byte Python
loops, and fell back to `[(0, len(data))]` (the *entire* file) whenever
exp01 found no low/structured-entropy regions. On the real ~1.52 GB MT5889
REE payload (which exp01 classified as a single high-entropy region), this
made exp02 attempt an unbounded brute-force scan that had to be interrupted
manually.

These tests cover: (1) the new implementation still produces the exact same
detection results as the original for identical input, (2) the fallback
path is bounded (head/tail, not the whole file), (3) any single region is
capped at max_region_scan_bytes regardless of its true size, and (4) a
moderately large file completes fast enough to prove runtime no longer
scales with file size.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from mtklab.core.experiment import ExperimentContext, ProgressReporter
from mtklab.experiments.exp02_repeated_structures.exp02_repeated_structures import (
    Exp02RepeatedStructures,
)


def _make_structured_record(i: int) -> bytes:
    """64-byte record with 48 stable bytes (tag/version/enum/flag/padding)
    and 16 variable bytes -- 48/64 = 0.75 consistency, matching the
    default min_consistency=0.7 threshold."""
    rec = bytearray(64)
    rec[0] = 0xAB
    rec[1] = 0x01
    rec[2] = i % 3
    rec[3] = 0xFF if i % 2 == 0 else 0x00
    rec[48:64] = os.urandom(16)
    return bytes(rec)


def _make_table_dominant_payload(record_count: int = 4000) -> bytes:
    return b"".join(_make_structured_record(i) for i in range(record_count))


class TestFieldStats(unittest.TestCase):
    def setUp(self):
        self.exp = Exp02RepeatedStructures()

    def test_constant_column(self):
        stats = self.exp._field_stats(bytes([0xAB]) * 100)
        self.assertEqual(stats["unique"], 1)
        self.assertFalse(stats["all_zero"])

    def test_all_zero_column(self):
        stats = self.exp._field_stats(bytes([0x00]) * 100)
        self.assertTrue(stats["all_zero"])
        self.assertEqual(stats["zero_ratio"], 1.0)

    def test_high_variance_column(self):
        stats = self.exp._field_stats(bytes(range(256)))
        self.assertEqual(stats["unique"], 256)
        self.assertFalse(stats["all_zero"])

    def test_empty_column(self):
        stats = self.exp._field_stats(b"")
        self.assertEqual(stats["unique"], 0)
        self.assertTrue(stats["all_zero"])


class TestAnalyzeRecords(unittest.TestCase):
    def setUp(self):
        self.exp = Exp02RepeatedStructures()

    def test_none_when_too_few_records(self):
        result = self.exp._analyze_records(b"\x00" * 100, 0, 64, min_records=3)
        self.assertIsNone(result)

    def test_detects_table_dominant_window(self):
        data = _make_table_dominant_payload(record_count=4000)
        result = self.exp._analyze_records(data, base_offset=0x1000, record_size=64, min_records=3)
        self.assertIsNotNone(result)
        self.assertEqual(result["offset"], 0x1000)
        self.assertEqual(result["record_size"], 64)
        self.assertEqual(result["count"], 4000)
        self.assertGreaterEqual(result["consistency"], 0.7)
        self.assertEqual(len(result["field_pattern"]), 64)
        self.assertEqual(result["field_pattern"][0], "constant")
        self.assertEqual(result["field_pattern"][1], "constant")
        self.assertIn(result["field_pattern"][4], ("zero",))  # padding byte

    def test_matches_original_algorithm_output(self):
        """Locks in behavioral equivalence with the pre-rewrite
        _detect_repeated_records for identical input: same offset, size,
        record_size, count, consistency and field_pattern."""
        data = _make_table_dominant_payload(record_count=1000)

        # Reimplementation of the ORIGINAL per-byte-loop algorithm, kept
        # here (not imported) so this test still pins the contract even
        # after the original method is long gone from the module.
        def original_detect(data, base_offset, record_size, min_consistency, min_records):
            n = len(data)
            max_records = n // record_size
            if max_records < min_records:
                return []
            field_stats = []
            for pos in range(record_size):
                values = []
                for i in range(max_records):
                    idx = i * record_size + pos
                    if idx < n:
                        values.append(data[idx])
                if not values:
                    field_stats.append({"unique": 0, "all_zero": True, "zero_ratio": 1.0})
                    continue
                unique_vals = set(values)
                zero_count = values.count(0)
                all_zero = zero_count == len(values)
                field_stats.append({
                    "unique": len(unique_vals),
                    "all_zero": all_zero,
                    "zero_ratio": zero_count / len(values),
                })
            stable = sum(1 for fs in field_stats if fs["unique"] <= 4 or fs["all_zero"])
            consistency = stable / record_size
            if consistency < min_consistency:
                return []
            field_pattern = []
            for fs in field_stats:
                if fs["all_zero"]:
                    field_pattern.append("zero")
                elif fs["unique"] == 1:
                    field_pattern.append("constant")
                elif fs["unique"] <= 4:
                    field_pattern.append("low_variance")
                elif fs["zero_ratio"] > 0.8:
                    field_pattern.append("mostly_zero")
                else:
                    field_pattern.append("variable")
            return [{
                "offset": base_offset, "size": record_size * max_records,
                "record_size": record_size, "count": max_records,
                "consistency": consistency, "field_pattern": field_pattern,
            }]

        for record_size in (32, 64, 128):
            old = original_detect(data, 0, record_size, 0.7, 3)
            new = self.exp._analyze_records(data, 0, record_size, 3)
            new = [new] if (new is not None and new["consistency"] >= 0.7) else []
            self.assertEqual(len(old), len(new), f"mismatch at record_size={record_size}")
            if old:
                self.assertEqual(old[0], new[0], f"output mismatch at record_size={record_size}")


class TestBoundedFallbackRegions(unittest.TestCase):
    def setUp(self):
        self.exp = Exp02RepeatedStructures()

    def test_small_file_single_head_region(self):
        regions = self.exp._bounded_fallback_regions(file_size=1000, fallback_bytes=4096)
        self.assertEqual(regions, [(0, 1000)])

    def test_file_up_to_2x_fallback_no_tail(self):
        # file_size == fallback_bytes * 2 exactly: guard is strict '>', so
        # still head-only (no double-counting the same bytes as head+tail).
        regions = self.exp._bounded_fallback_regions(file_size=8192, fallback_bytes=4096)
        self.assertEqual(regions, [(0, 4096)])

    def test_large_file_gets_head_and_tail(self):
        file_size = 10 * 1024 * 1024
        fallback_bytes = 4096
        regions = self.exp._bounded_fallback_regions(file_size, fallback_bytes)
        self.assertEqual(len(regions), 2)
        head, tail = regions
        self.assertEqual(head, (0, fallback_bytes))
        self.assertEqual(tail, (file_size - fallback_bytes, file_size))
        # Never larger than fallback_bytes each, never the whole file.
        for start, end in regions:
            self.assertLessEqual(end - start, fallback_bytes)


class TestRunEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.artifacts_dir = self.tmpdir / "artifacts"
        self.artifacts_dir.mkdir()

    def _make_ctx(self, ree_path: Path, shared_data: dict) -> ExperimentContext:
        return ExperimentContext(
            firmware_path=ree_path,
            ree_payload_path=ree_path,
            config={},
            evidence_db=None,
            artifacts_dir=self.artifacts_dir,
            shared_data=shared_data,
            progress=ProgressReporter(),
            logger=__import__("logging").getLogger("mtklab.test"),
        )

    def test_missing_payload_fails_cleanly(self):
        ctx = self._make_ctx(self.tmpdir / "does_not_exist.bin", {})
        result = Exp02RepeatedStructures().run(ctx)
        self.assertEqual(result.status, "failed")

    def test_fallback_path_is_bounded_and_fast_on_large_file(self):
        """A file much larger than max_region_scan_bytes must still
        complete quickly when exp01 supplied no regions -- this is the
        exact scenario that had to be interrupted manually on the real
        1.52 GB firmware payload."""
        payload_path = self.tmpdir / "large.bin"
        # 20 MiB of high-entropy data with no real structure: large enough
        # that the *original* per-byte-loop whole-file fallback took ~80s
        # in local benchmarking; the new bounded fallback should be near
        # instant regardless.
        with payload_path.open("wb") as f:
            f.write(os.urandom(20 * 1024 * 1024))

        exp = Exp02RepeatedStructures()
        ctx = self._make_ctx(payload_path, shared_data={})  # exp01 found nothing

        t0 = time.time()
        result = exp.run(ctx)
        elapsed = time.time() - t0

        self.assertLess(elapsed, 5.0, "fallback scan should be bounded, not proportional to file size")
        self.assertFalse(result.metadata["regions_from_exp01"])
        # 20 MiB > 2x fallback_bytes(4 MiB) -> bounded head AND tail regions,
        # never a single region spanning the whole 20 MiB file.
        self.assertEqual(result.metadata["regions_scanned"], 2)

    def test_max_region_scan_bytes_caps_a_huge_region_and_flags_truncation(self):
        payload_path = self.tmpdir / "region_test.bin"
        table = _make_table_dominant_payload(record_count=4000)  # 256,000 bytes
        with payload_path.open("wb") as f:
            f.write(table)
            f.write(os.urandom(2 * 1024 * 1024))  # region extends well past the table

        exp = Exp02RepeatedStructures()
        exp.parameters = dict(exp.parameters, max_region_scan_bytes=64 * 1024)  # force truncation

        regions_csv = self.tmpdir / "regions.csv"
        region_end = len(table) + 2 * 1024 * 1024
        with regions_csv.open("w", newline="") as f:
            f.write("start,end,class\n")
            f.write(f"0x00000000,0x{region_end:08X},structured/text/tables\n")

        ctx = self._make_ctx(
            payload_path,
            shared_data={"exp01_entropy_landscape": {"artifacts": {"regions_csv": str(regions_csv)}}},
        )
        result = exp.run(ctx)
        self.assertEqual(result.metadata["regions_truncated"], 1)

    def test_normal_path_detects_and_reports_table(self):
        payload_path = self.tmpdir / "table.bin"
        table = _make_table_dominant_payload(record_count=4000)
        payload_path.write_bytes(table)

        regions_csv = self.tmpdir / "regions.csv"
        with regions_csv.open("w", newline="") as f:
            f.write("start,end,class\n")
            f.write(f"0x00000000,0x{len(table):08X},structured/text/tables\n")

        exp = Exp02RepeatedStructures()
        ctx = self._make_ctx(
            payload_path,
            shared_data={"exp01_entropy_landscape": {"artifacts": {"regions_csv": str(regions_csv)}}},
        )
        result = exp.run(ctx)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.metadata["regions_from_exp01"])
        self.assertGreater(len(result.findings), 0)
        self.assertEqual(len(result.findings), len(result.evidences))
        self.assertIn("tables_csv", result.artifacts)
        self.assertTrue(result.artifacts["tables_csv"].exists())

    def test_tiny_quick_sample_bytes_does_not_cause_false_negative(self):
        """quick_sample_bytes smaller than record_size*min_records for some
        candidate must fall through to the full-window check rather than
        silently rejecting a real table (see run()'s `len(sample) >=
        record_size * min_records` guard)."""
        payload_path = self.tmpdir / "table.bin"
        table = _make_table_dominant_payload(record_count=4000)
        payload_path.write_bytes(table)

        regions_csv = self.tmpdir / "regions.csv"
        with regions_csv.open("w", newline="") as f:
            f.write("start,end,class\n")
            f.write(f"0x00000000,0x{len(table):08X},structured/text/tables\n")

        exp = Exp02RepeatedStructures()
        # Smaller than 1024 (largest default record_size) * 3 (min_records).
        exp.parameters = dict(exp.parameters, quick_sample_bytes=256)
        ctx = self._make_ctx(
            payload_path,
            shared_data={"exp01_entropy_landscape": {"artifacts": {"regions_csv": str(regions_csv)}}},
        )
        result = exp.run(ctx)
        self.assertGreater(len(result.findings), 0)


if __name__ == "__main__":
    unittest.main()
