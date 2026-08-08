"""Exp02 Repeated Structures - Detects fixed-size record arrays in low-entropy regions."""

import csv
import mmap
import uuid
from pathlib import Path
from typing import Optional

from mtklab.experiments import Experiment, ExperimentContext, ExperimentResult
from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind
from mtklab.utils import json as json_utils


class Exp02RepeatedStructures(Experiment):
    """Scans low-entropy regions for fixed-size record arrays (partition tables, cert chains)."""
    
    experiment_id = "exp02_repeated_structures"
    display_name = "Repeated Structure Detector"
    description = "Scans low-entropy regions for fixed-size record arrays (partition tables, cert chains)"
    version = "2.0.0"
    requires = ["exp01_entropy_landscape"]
    parameters = {
        "record_sizes": [16, 24, 32, 40, 48, 56, 64, 80, 96, 128, 192, 256, 384, 512, 768, 1024],
        "min_consistency": 0.7,
        "min_records": 3,
        "search_in_regions": "low_entropy",
        # --- Scalability bounds (MTKLAB-002 real-firmware follow-up) ---
        # These cap total bytes touched so runtime and memory stay bounded
        # regardless of firmware size, instead of scaling with it. See
        # docs/implementation for the O(region_size x record_sizes) issue
        # this replaces (real MT5889 REE payload: ~1.52 GB, single
        # high-entropy region -> unbounded brute-force scan had to be
        # interrupted).
        #
        # IMPORTANT: none of these bounds assume WHERE inside a region or
        # file a structure is located. When a region exceeds
        # max_region_scan_bytes, coverage is spread evenly across its full
        # span (see _tile_region()) rather than only examining its prefix
        # or a fixed head/tail -- Exp02 is a generic-core experiment and
        # must not silently encode vendor/layout assumptions (that belongs
        # in vendor-specific modules / targeted experiments instead).
        "max_region_scan_bytes": 8 * 1024 * 1024,     # hard cap analyzed per region (8 MiB)
        "tile_bytes": 256 * 1024,                      # analysis window size when a region is tiled (256 KiB)
        "max_total_scan_bytes": 32 * 1024 * 1024,      # aggregate cap across ALL regions in one run (32 MiB)
    }
    
    def run(self, ctx: ExperimentContext) -> ExperimentResult:
        # Load REE payload
        ree_path = ctx.ree_payload_path
        if not ree_path.exists():
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="failed",
                summary=f"REE payload not found at {ree_path}",
                errors=[f"File not found: {ree_path}"],
            )

        file_size = ree_path.stat().st_size

        # mmap.mmap(fd, 0, ...) raises ValueError on a genuinely empty file;
        # handle it explicitly rather than letting that exception surface,
        # and there is nothing to scan anyway.
        if file_size == 0:
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="partial",
                summary="REE payload is empty (0 bytes); nothing to scan.",
                metadata={"regions_scanned": 0, "file_size": 0},
            )

        record_sizes = self.parameters.get("record_sizes", [32, 64, 128, 256, 512])
        min_consistency = self.parameters.get("min_consistency", 0.7)
        min_records = self.parameters.get("min_records", 3)
        max_region_scan_bytes = self.parameters.get("max_region_scan_bytes", 8 * 1024 * 1024)
        tile_bytes = self.parameters.get("tile_bytes", 256 * 1024)
        max_total_scan_bytes = self.parameters.get("max_total_scan_bytes", 32 * 1024 * 1024)
        min_record_size = min(record_sizes)

        # Get low-entropy regions from exp01 via shared_data
        low_entropy_regions = self._get_low_entropy_regions(ctx)
        regions_from_exp01 = bool(low_entropy_regions)

        if not regions_from_exp01:
            # exp01 found no empty/padding or structured/text/tables regions
            # (e.g. the entire payload was classified as one high-entropy
            # region). Treat the whole file as a single region and let the
            # SAME bounded-tiling logic below handle it like any other
            # oversized region: distributed, budget-respecting coverage
            # across the full file, not a scan of the whole thing and not a
            # scan of only a fixed head/tail. Exp02 makes no assumption
            # about where a structure is located.
            ctx.logger.warning(
                "No low-entropy regions found in shared_data from exp01; falling back to "
                f"a bounded, distributed scan of up to {max_total_scan_bytes} bytes spread "
                "across the full payload (start, middle, and end all get sampled -- exp02 "
                "does not assume structures live at any particular location). This is not "
                "exhaustive coverage of a large high-entropy payload; check "
                "'budget_exhausted' / 'regions_tiled' in this result's metadata, and run a "
                "targeted, offset-based analysis if full coverage is required."
            )
            low_entropy_regions = [(0, file_size)]

        findings = []
        evidences = []
        all_tables = []
        regions_tiled = 0
        regions_skipped_budget = 0
        total_bytes_analyzed = 0

        num_regions = len(low_entropy_regions)
        # Fair up-front share of the global budget per region, still capped
        # by max_region_scan_bytes. This is a ceiling, not a pre-commitment:
        # a region that needs less leaves the *actual* running
        # remaining_total_budget below untouched for later regions.
        per_region_cap = min(
            max_region_scan_bytes,
            max(tile_bytes, max_total_scan_bytes // max(1, num_regions)),
        )
        remaining_total_budget = max_total_scan_bytes

        with ree_path.open("rb") as fh:
            # mmap avoids loading the (possibly multi-gigabyte) file into
            # memory up front; only the bounded windows we actually slice
            # below get paged in by the OS.
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for region_start, region_end in low_entropy_regions:
                    region_size = region_end - region_start

                    if region_size < min_records * min_record_size:
                        continue

                    if remaining_total_budget < min_records * min_record_size:
                        # Global budget is exhausted: stop, and say so
                        # explicitly in the result rather than silently
                        # under-covering the remaining regions.
                        regions_skipped_budget += 1
                        continue

                    effective_cap = min(per_region_cap, remaining_total_budget)

                    if region_size <= effective_cap:
                        # Fits entirely within budget: scan it whole, exactly
                        # as a non-truncated region always has. No tiling
                        # needed or performed.
                        windows = [(region_start, region_end)]
                        tiled = False
                    else:
                        # Region exceeds the budget: spread bounded windows
                        # evenly across its FULL SPAN (not just the prefix)
                        # so a structure anywhere in the region has the same
                        # chance of being sampled.
                        windows = self._tile_region(region_start, region_end, tile_bytes, effective_cap)
                        tiled = True
                        regions_tiled += 1

                    region_bytes_analyzed = 0

                    for w_start, w_end in windows:
                        window = bytes(mm[w_start:w_end])
                        region_bytes_analyzed += len(window)

                        for record_size in record_sizes:
                            if len(window) < record_size * min_records:
                                continue

                            table = self._analyze_records(window, w_start, record_size, min_records)
                            if table is None or table["consistency"] < min_consistency:
                                continue

                            table["region_start"] = region_start
                            table["region_end"] = region_end
                            table["window_start"] = w_start
                            table["window_end"] = w_end
                            table["scanned_bytes"] = len(window)
                            table["tiled"] = tiled
                            all_tables.append(table)

                            # Create finding for each table
                            finding = Finding(
                                finding_id=str(uuid.uuid4()),
                                experiment_id=self.experiment_id,
                                kind=FindingKind.TABLE,
                                offset=table["offset"],
                                size=table["size"],
                                confidence=ConfidenceLevel.CANDIDATE,
                                label=f"Repeated structure: {table['record_size']}B x {table['count']}",
                                description=(
                                    f"Fixed-size records at 0x{table['offset']:08X}: {table['count']} records "
                                    f"of {table['record_size']}B (consistency: {table['consistency']:.2f})"
                                    + (
                                        " [found via distributed sampling within a larger region; "
                                        "region not exhaustively scanned]"
                                        if tiled else ""
                                    )
                                ),
                                metadata={
                                    "record_size": table["record_size"],
                                    "record_count": table["count"],
                                    "consistency": table["consistency"],
                                    "field_pattern": table["field_pattern"],
                                    "scanned_bytes": table["scanned_bytes"],
                                    "tiled": tiled,
                                },
                            )
                            findings.append(finding)

                            # Evidence for this table
                            evidence = Evidence(
                                evidence_id=str(uuid.uuid4()),
                                experiment_id=self.experiment_id,
                                evidence_type=EvidenceType.STRUCTURAL_PATTERN,
                                confidence=ConfidenceLevel.CANDIDATE,
                                description=f"Repeated {table['record_size']}-byte records with {table['consistency']:.0%} consistency",
                                data={
                                    "record_size": table["record_size"],
                                    "count": table["count"],
                                    "consistency": table["consistency"],
                                    "field_pattern": table["field_pattern"],
                                },
                                source_offset=table["offset"],
                                source_size=table["size"],
                                tags=["repeated_structure", f"size_{table['record_size']}"]
                            )
                            evidences.append(evidence)

                    total_bytes_analyzed += region_bytes_analyzed
                    remaining_total_budget -= region_bytes_analyzed
        
        # Write artifacts
        artifacts = {}
        
        if all_tables:
            csv_path = ctx.artifacts_dir / "tables.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "offset", "size", "record_size", "count", "consistency",
                    "region_start", "region_end", "window_start", "window_end",
                    "scanned_bytes", "tiled", "field_pattern",
                ])
                writer.writeheader()
                for t in all_tables:
                    row = {k: v for k, v in t.items() if k != "field_pattern"}
                    row["offset"] = f"0x{row['offset']:08X}"
                    row["region_start"] = f"0x{row['region_start']:08X}"
                    row["region_end"] = f"0x{row['region_end']:08X}"
                    row["window_start"] = f"0x{row['window_start']:08X}"
                    row["window_end"] = f"0x{row['window_end']:08X}"
                    row["field_pattern"] = json_utils.dumps(t["field_pattern"])
                    writer.writerow(row)
            artifacts["tables_csv"] = csv_path
        
        return ExperimentResult(
            experiment_id=self.experiment_id,
            status="success" if findings else "partial",
            summary=(
                f"Structure detection complete: {len(all_tables)} tables found across "
                f"{num_regions} region(s) ({regions_tiled} tiled due to size, "
                f"{regions_skipped_budget} skipped -- total scan budget exhausted)"
                if regions_skipped_budget
                else (
                    f"Structure detection complete: {len(all_tables)} tables found across "
                    f"{num_regions} region(s) ({regions_tiled} tiled due to size)"
                )
            ),
            findings=findings,
            evidences=evidences,
            artifacts=artifacts,
            metadata={
                "regions_scanned": num_regions,
                "regions_from_exp01": regions_from_exp01,
                "regions_tiled": regions_tiled,
                "regions_skipped_due_to_budget": regions_skipped_budget,
                "budget_exhausted": regions_skipped_budget > 0,
                "max_region_scan_bytes": max_region_scan_bytes,
                "max_total_scan_bytes": max_total_scan_bytes,
                "tile_bytes": tile_bytes,
                "total_bytes_analyzed": total_bytes_analyzed,
                "tables_found": len(all_tables),
                "record_sizes_tested": record_sizes,
                "min_consistency": min_consistency,
            },
        )
    
    def _get_low_entropy_regions(self, ctx: ExperimentContext) -> list[tuple[int, int]]:
        """Extract low-entropy regions from exp01 shared data."""
        exp01_data = ctx.shared_data.get("exp01_entropy_landscape", {})
        artifacts = exp01_data.get("artifacts", {})
        
        regions_path = artifacts.get("regions_csv")
        if regions_path and Path(regions_path).exists():
            regions = []
            with Path(regions_path).open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["class"] in ("empty/padding", "structured/text/tables"):
                        start = int(row["start"], 16) if row["start"].startswith("0x") else int(row["start"])
                        end = int(row["end"], 16) if row["end"].startswith("0x") else int(row["end"])
                        regions.append((start, end))
            return regions
        
        return []

    def _tile_region(
        self, region_start: int, region_end: int, tile_bytes: int, budget_bytes: int
    ) -> list[tuple[int, int]]:
        """Distribute analysis windows evenly across a region's FULL SPAN
        when the region is larger than the byte budget allows fully
        covering, instead of only examining its prefix.

        This is the single, generic mechanism that replaced two earlier,
        narrower heuristics:
          - a "quick sample" hard-reject on the first quick_sample_bytes of
            a window, which could silently skip a record_size whose real
            periodicity only appears later in the region;
          - a head/tail-only fallback (_bounded_fallback_regions), which
            assumed structures live only at the start or end of the file --
            a MediaTek/MT5889-specific layout assumption that does not
            belong in this generic, vendor-independent experiment.

        No assumption is made about WHERE inside [region_start, region_end)
        a structure might be: tiles are spread evenly across the whole
        span, so a structure near the start, middle, or end all have the
        same chance of falling inside a sampled tile. Total bytes examined
        is bounded by budget_bytes regardless of how large the region is.
        """
        region_size = region_end - region_start
        tile_bytes = max(1, min(tile_bytes, budget_bytes))
        max_tiles = max(1, budget_bytes // tile_bytes)

        if max_tiles <= 1:
            # Budget can't even fit a second tile alongside the first; the
            # best effort under such a tight budget is a single tile at the
            # region's start. This only happens with a deliberately tiny
            # budget configuration, not by default.
            return [(region_start, region_start + min(tile_bytes, region_size))]

        stride = (region_size - tile_bytes) / (max_tiles - 1)
        tiles = []
        seen_starts = set()
        for i in range(max_tiles):
            start = region_start + round(i * stride)
            start = min(start, region_end - tile_bytes)
            start = max(start, region_start)
            if start in seen_starts:
                # Region only slightly larger than the budget: consecutive
                # strides can round to the same start. Skip the duplicate
                # rather than analyzing the same bytes twice.
                continue
            seen_starts.add(start)
            tiles.append((start, start + tile_bytes))
        return tiles

    def _field_stats(self, column: bytes) -> dict:
        """Value-distribution stats for one within-record byte position.

        `column` is produced by the caller via a single strided slice
        (`data[pos:limit:record_size]`), i.e. one C-level operation per field
        position rather than `record_size * (len(data)//record_size)`
        individual Python-level byte lookups. Only fast, built-in bytes
        operations (`.count()`, `set()`) are used here -- no per-byte Python
        loop and no per-value entropy/log2 computation, which the original
        implementation computed but never actually used in its consistency
        or field_pattern decisions.
        """
        n = len(column)
        if n == 0:
            return {"unique": 0, "all_zero": True, "zero_ratio": 1.0}
        zero_count = column.count(0)
        return {
            "unique": len(set(column)),
            "all_zero": zero_count == n,
            "zero_ratio": zero_count / n,
        }

    def _analyze_records(
        self,
        data: bytes,
        base_offset: int,
        record_size: int,
        min_records: int,
    ) -> Optional[dict]:
        """Compute per-field consistency stats for one candidate record_size
        over `data` (a bounded, already-materialized bytes window -- never
        the raw region size or the whole file). Returns None if `data` can't
        satisfy `min_records` at this `record_size`."""
        n = len(data)
        max_records = n // record_size
        if max_records < min_records:
            return None

        limit = max_records * record_size
        field_stats = [
            self._field_stats(data[pos:limit:record_size]) for pos in range(record_size)
        ]

        stable_positions = sum(1 for fs in field_stats if fs["unique"] <= 4 or fs["all_zero"])
        consistency = stable_positions / record_size

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

        return {
            "offset": base_offset,
            "size": record_size * max_records,
            "record_size": record_size,
            "count": max_records,
            "consistency": consistency,
            "field_pattern": field_pattern,
        }