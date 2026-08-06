"""Exp02 Repeated Structures - Detects fixed-size record arrays in low-entropy regions."""

import uuid
import csv
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
    version = "1.0.0"
    requires = ["exp01_entropy_landscape"]
    parameters = {
        "record_sizes": [16, 24, 32, 40, 48, 56, 64, 80, 96, 128, 192, 256, 384, 512, 768, 1024],
        "min_consistency": 0.7,
        "min_records": 3,
        "search_in_regions": "low_entropy",
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
        
        data = ree_path.read_bytes()
        
        # Get low-entropy regions from exp01 via shared_data
        low_entropy_regions = self._get_low_entropy_regions(ctx)
        
        if not low_entropy_regions:
            ctx.logger.warning("No low-entropy regions found in shared_data from exp01")
            low_entropy_regions = [(0, len(data))]  # Fallback: scan entire file
        
        findings = []
        evidences = []
        all_tables = []
        
        record_sizes = self.parameters.get("record_sizes", [32, 64, 128, 256, 512])
        min_consistency = self.parameters.get("min_consistency", 0.7)
        min_records = self.parameters.get("min_records", 3)
        
        for region_start, region_end in low_entropy_regions:
            region_data = data[region_start:region_end]
            region_size = len(region_data)
            
            if region_size < min_records * min(record_sizes):
                continue
            
            # Test each record size
            for record_size in record_sizes:
                if region_size < record_size * min_records:
                    continue
                
                tables = self._detect_repeated_records(
                    region_data, region_start, record_size, min_consistency, min_records
                )
                
                for table in tables:
                    table["region_start"] = region_start
                    table["region_end"] = region_end
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
                        description=f"Fixed-size records at 0x{table['offset']:08X}: {table['count']} records of {table['record_size']}B (consistency: {table['consistency']:.2f})",
                        metadata={
                            "record_size": table["record_size"],
                            "record_count": table["count"],
                            "consistency": table["consistency"],
                            "field_pattern": table["field_pattern"],
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
                    "region_start", "region_end", "field_pattern"
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
            summary=f"Structure detection complete: {len(all_tables)} tables found in {len(low_entropy_regions)} low-entropy regions",
            findings=findings,
            evidences=evidences,
            artifacts=artifacts,
            metadata={
                "regions_scanned": len(low_entropy_regions),
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
    
    def _detect_repeated_records(
        self, 
        data: bytes, 
        base_offset: int, 
        record_size: int, 
        min_consistency: float,
        min_records: int
    ) -> list[dict]:
        """Detect repeated fixed-size records in data."""
        n = len(data)
        max_records = n // record_size
        
        if max_records < min_records:
            return []
        
        # Analyze each position within the record
        field_stats = []
        for pos in range(record_size):
            values = []
            for i in range(max_records):
                idx = i * record_size + pos
                if idx < n:
                    values.append(data[idx])
            
            if not values:
                field_stats.append({"position": pos, "unique": 0, "entropy": 0, "all_zero": True})
                continue
            
            unique_vals = set(values)
            zero_count = values.count(0)
            all_zero = zero_count == len(values)
            
            # Calculate entropy of values at this position
            from collections import Counter
            counts = Counter(values)
            entropy = 0
            import math
            for count in counts.values():
                p = count / len(values)
                entropy -= p * math.log2(p) if p > 0 else 0
            
            field_stats.append({
                "position": pos,
                "unique": len(unique_vals),
                "entropy": entropy,
                "all_zero": all_zero,
                "zero_ratio": zero_count / len(values),
            })
        
        # Determine consistency: how many positions have stable patterns
        stable_positions = sum(1 for fs in field_stats if fs["unique"] <= 4 or fs["all_zero"])
        consistency = stable_positions / record_size
        
        if consistency < min_consistency:
            return []
        
        # Build field pattern description
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
            "offset": base_offset,
            "size": record_size * max_records,
            "record_size": record_size,
            "count": max_records,
            "consistency": consistency,
            "field_pattern": field_pattern,
        }]