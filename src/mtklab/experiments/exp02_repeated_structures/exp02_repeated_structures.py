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
        # These cap total bytes touched per region so runtime and memory stay
        # flat regardless of firmware size, instead of scaling with it. See
        # docs/implementation for the O(region_size x record_sizes) issue this
        # replaces (real MT5889 REE payload: ~1.52 GB, single high-entropy
        # region -> unbounded brute-force scan had to be interrupted).
        "max_region_scan_bytes": 8 * 1024 * 1024,      # hard cap analyzed per region (8 MiB)
        "quick_sample_bytes": 64 * 1024,                # cheap pre-filter sample (64 KiB)
        "no_regions_fallback_bytes": 4 * 1024 * 1024,   # bound for the "exp01 found nothing" fallback
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

        record_sizes = self.parameters.get("record_sizes", [32, 64, 128, 256, 512])
        min_consistency = self.parameters.get("min_consistency", 0.7)
        min_records = self.parameters.get("min_records", 3)
        max_region_scan_bytes = self.parameters.get("max_region_scan_bytes", 8 * 1024 * 1024)
        quick_sample_bytes = self.parameters.get("quick_sample_bytes", 64 * 1024)
        fallback_bytes = self.parameters.get("no_regions_fallback_bytes", 4 * 1024 * 1024)

        # Get low-entropy regions from exp01 via shared_data
        low_entropy_regions = self._get_low_entropy_regions(ctx)
        regions_from_exp01 = bool(low_entropy_regions)

        if not regions_from_exp01:
            # exp01 found no empty/padding or structured/text/tables regions
            # (e.g. the entire payload was classified as one high-entropy
            # region). Do NOT fall back to scanning the whole file -- that is
            # exactly the brute-force full-file scan this rewrite exists to
            # avoid. Structural tables (partition tables, headers, cert
            # chains) are conventionally anchored at the start or end of a
            # firmware image, so fall back to a bounded scan of the head and
            # tail instead. This is also what a future MTKLAB-013 MediaTek
            # header parser around offset 0x500 would want scanned.
            ctx.logger.warning(
                "No low-entropy regions found in shared_data from exp01; falling back to "
                f"a bounded scan of the first {fallback_bytes} bytes"
                + (f" and last {fallback_bytes} bytes " if file_size > fallback_bytes * 2 else " ")
                + "of the payload instead of the full file. Run a targeted, offset-based "
                "analysis for full coverage of large high-entropy payloads."
            )
            low_entropy_regions = self._bounded_fallback_regions(file_size, fallback_bytes)

        findings = []
        evidences = []
        all_tables = []
        regions_truncated = 0

        with ree_path.open("rb") as fh:
            # mmap avoids loading the (possibly multi-gigabyte) file into
            # memory up front; only the bounded windows we actually slice
            # below get paged in by the OS.
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for region_start, region_end in low_entropy_regions:
                    region_size = region_end - region_start

                    if region_size < min_records * min(record_sizes):
                        continue

                    # Hard cap: never analyze more than max_region_scan_bytes
                    # of any single region, no matter how large the region
                    # (or the fallback file-scan) actually is.
                    scan_size = min(region_size, max_region_scan_bytes)
                    truncated = scan_size < region_size
                    if truncated:
                        regions_truncated += 1

                    # ONE bounded copy per region (<= max_region_scan_bytes).
                    # All further analysis works on this small in-memory
                    # bytes object with fast strided slicing -- never on the
                    # raw region size or the whole file.
                    window = bytes(mm[region_start:region_start + scan_size])
                    sample = window[: min(quick_sample_bytes, scan_size)]

                    for record_size in record_sizes:
                        if scan_size < record_size * min_records:
                            continue

                        # Cheap reject on a small sample before paying for
                        # the full (still bounded) window pass -- most
                        # (region, record_size) combinations aren't
                        # periodic and bail out right here. Skipped only if
                        # the sample itself is too small to fairly judge
                        # this record_size (avoids false negatives from an
                        # undersized quick_sample_bytes).
                        if len(sample) >= record_size * min_records:
                            quick = self._analyze_records(sample, region_start, record_size, min_records)
                            if quick is None or quick["consistency"] < min_consistency:
                                continue

                        table = self._analyze_records(window, region_start, record_size, min_records)
                        if table is None or table["consistency"] < min_consistency:
                            continue

                        table["region_start"] = region_start
                        table["region_end"] = region_end
                        table["scanned_bytes"] = scan_size
                        table["truncated"] = truncated
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
                                + (" [region truncated to scan bound; table may extend further]" if truncated else "")
                            ),
                            metadata={
                                "record_size": table["record_size"],
                                "record_count": table["count"],
                                "consistency": table["consistency"],
                                "field_pattern": table["field_pattern"],
                                "scanned_bytes": scan_size,
                                "truncated": truncated,
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
        
        # Write artifacts
        artifacts = {}
        
        if all_tables:
            csv_path = ctx.artifacts_dir / "tables.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "offset", "size", "record_size", "count", "consistency", 
                    "region_start", "region_end", "scanned_bytes", "truncated", "field_pattern"
                ])
                writer.writeheader()
                for t in all_tables:
                    row = {k: v for k, v in t.items() if k != "field_pattern"}
                    row["offset"] = f"0x{row['offset']:08X}"
                    row["region_start"] = f"0x{row['region_start']:08X}"
                    row["region_end"] = f"0x{row['region_end']:08X}"
                    row["field_pattern"] = json_utils.dumps(t["field_pattern"])
                    writer.writerow(row)
            artifacts["tables_csv"] = csv_path
        
        return ExperimentResult(
            experiment_id=self.experiment_id,
            status="success" if findings else "partial",
            summary=(
                f"Structure detection complete: {len(all_tables)} tables found in "
                f"{len(low_entropy_regions)} region(s) scanned (bounded to "
                f"{max_region_scan_bytes} bytes/region)"
            ),
            findings=findings,
            evidences=evidences,
            artifacts=artifacts,
            metadata={
                "regions_scanned": len(low_entropy_regions),
                "regions_from_exp01": regions_from_exp01,
                "regions_truncated": regions_truncated,
                "max_region_scan_bytes": max_region_scan_bytes,
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

    def _bounded_fallback_regions(self, file_size: int, fallback_bytes: int) -> list[tuple[int, int]]:
        """Bounded head/tail regions used when exp01 found no candidate
        regions at all (e.g. the whole payload was classified as one
        high-entropy region). Deliberately NOT `[(0, file_size)]`: structural
        tables in firmware images conventionally sit at the start (headers,
        partition tables) or end (trailers, signatures) rather than being
        scattered through a multi-gigabyte high-entropy body, so bounding to
        the head and tail keeps runtime flat while still covering the
        realistic locations -- see config/firmware.yaml known_structures
        (crypto/MTK headers all sit within the first 0x1000 bytes)."""
        head_end = min(fallback_bytes, file_size)
        regions = [(0, head_end)]
        if file_size > fallback_bytes * 2:
            tail_start = max(head_end, file_size - fallback_bytes)
            regions.append((tail_start, file_size))
        return regions

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