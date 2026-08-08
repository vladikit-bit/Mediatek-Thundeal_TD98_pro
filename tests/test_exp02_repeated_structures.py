"""Tests for the scalable, unbiased-coverage rewrite of exp02_repeated_structures.

Background: the original implementation analyzed a candidate region with
`for pos in range(record_size): for i in range(max_records): ...`, touching
every byte of the region once per candidate record_size via per-byte Python
loops, and fell back to `[(0, len(data))]` (the *entire* file) whenever
exp01 found no low/structured-entropy regions. On the real ~1.52 GB MT5889
REE payload (which exp01 classified as a single high-entropy region), this
made exp02 attempt an unbounded brute-force scan that had to be interrupted
manually.

A first scalability pass (mmap, max_region_scan_bytes, fast strided slicing
in _analyze_records/_field_stats) fixed the runtime problem but introduced
two false-negative risks, since fixed here:

  - a `quick_sample_bytes` hard-reject on only the first N bytes of a
    window could silently skip a record_size whose real periodicity only
    appears later in the region;
  - a `_bounded_fallback_regions()` head/tail-only fallback assumed
    structures live only at the start or end of the file -- a
    MediaTek/MT5889-specific layout assumption with no place in this
    generic, vendor-independent experiment.

Both are replaced by a single mechanism, `_tile_region()`: when a region
exceeds the byte budget, coverage is spread evenly across the region's FULL
SPAN (start, middle, and end all sampled) rather than concentrated at a
fixed prefix or head/tail. `max_total_scan_bytes` additionally bounds
aggregate work across all regions in one run, with any shortfall reported
via `budget_exhausted` / `regions_skipped_due_to_budget` rather than a
silent gap in coverage.

Correctness tests here avoid wall-clock assertions; boundedness is checked
structurally (bytes actually analyzed, region/tile counts). A separate,
clearly-labeled benchmark class exists for optional performance sanity
checks and is not part of the correctness contract.
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
    """Unchanged code path (explicitly preserved) -- still covered directly."""

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
    """Unchanged code path (explicitly preserved) -- still covered directly."""

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


class TestTileRegion(unittest.TestCase):
    """_tile_region() is the single mechanism that replaced both the
    quick_sample_bytes hard-reject and the head/tail-only fallback. These
    tests focus specifically on the property that motivated the review:
    coverage must span the region's FULL LENGTH, not just a fixed prefix,
    head, or tail."""

    def setUp(self):
        self.exp = Exp02RepeatedStructures()

    def test_tiles_span_full_region_not_just_prefix(self):
        tiles = self.exp._tile_region(region_start=0, region_end=1_000_000, tile_bytes=1000, budget_bytes=8000)
        self.assertGreaterEqual(len(tiles), 2)
        starts = [s for s, _ in tiles]
        # The whole point of this method: coverage must reach well past a
        # small fixed prefix, unlike the old scan_size-truncated window.
        self.assertGreater(max(starts), 100_000)
        for s, e in tiles:
            self.assertEqual(e - s, 1000)
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(e, 1_000_000)

    def test_last_tile_reaches_near_region_end(self):
        """Coverage must extend close to the end of the region, not stop
        after a fixed number of bytes from the start -- directly guards
        against reintroducing a prefix/head-only bias."""
        region_end = 5_000_000
        tiles = self.exp._tile_region(0, region_end, tile_bytes=1000, budget_bytes=10000)
        last_start, last_end = tiles[-1]
        self.assertGreater(last_end, region_end - 1000)

    def test_total_tiled_bytes_within_budget(self):
        tiles = self.exp._tile_region(0, 10_000_000, tile_bytes=2000, budget_bytes=20000)
        total = sum(e - s for s, e in tiles)
        self.assertLessEqual(total, 20000)

    def test_tiny_budget_still_returns_at_least_one_tile(self):
        tiles = self.exp._tile_region(0, 1_000_000, tile_bytes=5000, budget_bytes=100)
        self.assertEqual(len(tiles), 1)
        s, e = tiles[0]
        self.assertLessEqual(e - s, 100)

    def test_no_duplicate_tiles_when_region_barely_exceeds_budget(self):
        tiles = self.exp._tile_region(0, 10_001, tile_bytes=1000, budget_bytes=10000)
        starts = [s for s, _ in tiles]
        self.assertEqual(len(starts), len(set(starts)), "tile starts must be de-duplicated")

    def test_tiles_never_extend_past_region_bounds(self):
        tiles = self.exp._tile_region(region_start=500, region_end=1500, tile_bytes=100, budget_bytes=300)
        for s, e in tiles:
            self.assertGreaterEqual(s, 500)
            self.assertLessEqual(e, 1500)


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

    def test_empty_payload_handled_cleanly(self):
        """mmap.mmap(fd, 0, ...) raises ValueError on a genuinely empty
        file; run() must guard this explicitly rather than crash."""
        payload_path = self.tmpdir / "empty.bin"
        payload_path.write_bytes(b"")
        ctx = self._make_ctx(payload_path, {})

        result = Exp02RepeatedStructures().run(ctx)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.metadata["regions_scanned"], 0)
        self.assertEqual(len(result.findings), 0)
        self.assertEqual(len(result.errors), 0)

    def test_fallback_path_is_bounded_not_proportional_to_file_size(self):
        """A file much larger than the scan budget must still analyze only
        a bounded number of bytes when exp01 supplied no regions -- this is
        the exact scenario that had to be interrupted manually on the real
        1.52 GB firmware payload. Checked structurally (bytes analyzed),
        not via a wall-clock assertion."""
        payload_path = self.tmpdir / "large.bin"
        with payload_path.open("wb") as f:
            f.write(os.urandom(20 * 1024 * 1024))  # 20 MiB, no real structure

        exp = Exp02RepeatedStructures()
        ctx = self._make_ctx(payload_path, shared_data={})  # exp01 found nothing

        result = exp.run(ctx)

        self.assertFalse(result.metadata["regions_from_exp01"])
        self.assertEqual(result.metadata["regions_scanned"], 1)  # whole file = one region
        self.assertEqual(result.metadata["regions_tiled"], 1)    # region >> budget -> tiled
        self.assertLessEqual(
            result.metadata["total_bytes_analyzed"],
            result.metadata["max_total_scan_bytes"],
        )
        # The defining property: bytes actually analyzed must be small
        # relative to the 20 MiB file, i.e. genuinely bounded.
        self.assertLess(result.metadata["total_bytes_analyzed"], 20 * 1024 * 1024)

    def test_max_region_scan_bytes_caps_a_huge_region_and_flags_tiling(self):
        payload_path = self.tmpdir / "region_test.bin"
        table = _make_table_dominant_payload(record_count=4000)  # 256,000 bytes
        with payload_path.open("wb") as f:
            f.write(table)
            f.write(os.urandom(2 * 1024 * 1024))  # region extends well past the table

        exp = Exp02RepeatedStructures()
        exp.parameters = dict(exp.parameters, max_region_scan_bytes=64 * 1024, tile_bytes=16 * 1024)

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
        self.assertEqual(result.metadata["regions_tiled"], 1)
        self.assertTrue(any(f.metadata.get("tiled") for f in result.findings))

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
        self.assertEqual(result.metadata["regions_tiled"], 0)  # small region: no tiling needed
        self.assertGreater(len(result.findings), 0)
        self.assertEqual(len(result.findings), len(result.evidences))
        self.assertIn("tables_csv", result.artifacts)
        self.assertTrue(result.artifacts["tables_csv"].exists())

    def test_detects_structure_far_past_unrelated_prefix(self):
        """Regression test for the core false-negative concern: the
        beginning of a large region is unrelated (high-entropy) data, and a
        valid repeated-record table only starts well past where the OLD
        prefix-bounded window (or a quick-sample hard-reject) would ever
        have looked. The new tiled scan must still find it.

        Region layout: [40 KiB unrelated random data][~125 KiB real table].
        max_region_scan_bytes is deliberately set to 32 KiB -- smaller than
        the unrelated prefix alone -- so a prefix-only or head-only scan of
        this region would see NOTHING but noise and report zero findings.
        """
        noise_len = 40 * 1024
        table_bytes = _make_table_dominant_payload(record_count=2000)  # ~125,000 bytes
        payload = os.urandom(noise_len) + table_bytes
        payload_path = self.tmpdir / "structure_after_noise.bin"
        payload_path.write_bytes(payload)

        exp = Exp02RepeatedStructures()
        exp.parameters = dict(
            exp.parameters,
            max_region_scan_bytes=32 * 1024,   # < noise_len: old prefix-only scan finds nothing
            tile_bytes=8 * 1024,
            max_total_scan_bytes=256 * 1024,
        )

        regions_csv = self.tmpdir / "regions.csv"
        with regions_csv.open("w", newline="") as f:
            f.write("start,end,class\n")
            f.write(f"0x00000000,0x{len(payload):08X},structured/text/tables\n")

        ctx = self._make_ctx(
            payload_path,
            shared_data={"exp01_entropy_landscape": {"artifacts": {"regions_csv": str(regions_csv)}}},
        )
        result = exp.run(ctx)

        self.assertGreater(len(result.findings), 0, "structure past the unrelated prefix must still be found")
        self.assertEqual(result.metadata["regions_tiled"], 1)
        # At least one finding must actually fall within the real table's
        # true span, not merely exist by coincidence elsewhere.
        table_start = noise_len
        table_end = noise_len + len(table_bytes)
        self.assertTrue(
            any(table_start <= f.offset < table_end for f in result.findings),
            f"no finding overlaps the real table span [{table_start}, {table_end})",
        )

    def test_global_budget_is_reported_when_exhausted(self):
        """Many small regions whose combined size exceeds
        max_total_scan_bytes must not be silently under-covered -- the
        shortfall must be visible in metadata."""
        payload_path = self.tmpdir / "many_regions.bin"
        payload_path.write_bytes(os.urandom(2 * 1024 * 1024))

        exp = Exp02RepeatedStructures()
        exp.parameters = dict(
            exp.parameters,
            max_region_scan_bytes=4096,
            tile_bytes=1024,
            max_total_scan_bytes=8192,  # enough for only ~2 regions at the per-region cap
        )

        regions_csv = self.tmpdir / "regions.csv"
        with regions_csv.open("w", newline="") as f:
            f.write("start,end,class\n")
            # 20 disjoint regions, each individually well above the
            # min-records floor, far more than the tiny global budget
            # allows analyzing in full.
            for i in range(20):
                start = i * 100_000
                end = start + 50_000
                f.write(f"0x{start:08X},0x{end:08X},structured/text/tables\n")

        ctx = self._make_ctx(
            payload_path,
            shared_data={"exp01_entropy_landscape": {"artifacts": {"regions_csv": str(regions_csv)}}},
        )
        result = exp.run(ctx)

        self.assertLessEqual(result.metadata["total_bytes_analyzed"], exp.parameters["max_total_scan_bytes"])
        if result.metadata["regions_skipped_due_to_budget"] > 0:
            self.assertTrue(result.metadata["budget_exhausted"])


class TestPerformanceSanityBenchmark(unittest.TestCase):
    """Optional, clearly-separated performance sanity check -- NOT part of
    the correctness contract above. A generous bound here only guards
    against a catastrophic regression (e.g. accidentally reading the whole
    file again); it is not a precision timing assertion."""

    def test_large_file_fallback_completes_quickly(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            payload_path = tmpdir / "large.bin"
            with payload_path.open("wb") as f:
                f.write(os.urandom(20 * 1024 * 1024))

            artifacts_dir = tmpdir / "artifacts"
            artifacts_dir.mkdir()
            ctx = ExperimentContext(
                firmware_path=payload_path,
                ree_payload_path=payload_path,
                config={},
                evidence_db=None,
                artifacts_dir=artifacts_dir,
                shared_data={},
                progress=ProgressReporter(),
                logger=__import__("logging").getLogger("mtklab.test"),
            )

            t0 = time.time()
            Exp02RepeatedStructures().run(ctx)
            elapsed = time.time() - t0

            # Generous smoke-test bound (old algorithm measured ~80s on
            # just 20 MiB); not a tight performance assertion.
            self.assertLess(elapsed, 15.0)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
