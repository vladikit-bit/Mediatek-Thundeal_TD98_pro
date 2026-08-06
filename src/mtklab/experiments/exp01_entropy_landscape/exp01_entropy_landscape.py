"""Exp01 Entropy Landscape - Macro entropy scan of REE payload."""

import uuid
import csv
from pathlib import Path
from typing import Optional

from mtklab.experiments import Experiment, ExperimentContext, ExperimentResult
from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind
from mtklab.adapters import MStarEntropyAdapter, EntropyScanConfig


class Exp01EntropyLandscape(Experiment):
    """Shannon entropy scan of REE payload with 4KB windows to identify region boundaries."""
    
    experiment_id = "exp01_entropy_landscape"
    display_name = "Entropy Landscape (Macro)"
    description = "Shannon entropy scan of REE payload with 4KB windows to identify region boundaries"
    version = "1.0.0"
    requires = []
    parameters = {
        "window_size": 4096,
        "step_size": 4096,
        "high_entropy_threshold": 7.2,
        "output_regions_csv": True,
        "output_sparkline": True,
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
        
        ctx.logger.info(f"Reading REE payload: {ree_path} ({ree_path.stat().st_size:,} bytes)")
        data = ree_path.read_bytes()
        
        # Configure and run adapter
        config = EntropyScanConfig(
            window=self.parameters.get("window_size", 4096),
            step=self.parameters.get("step_size", 4096),
            high_entropy_threshold=self.parameters.get("high_entropy_threshold", 7.2),
        )
        
        adapter = MStarEntropyAdapter(config)
        ctx.logger.info("Running entropy scan...")
        points, evidences = adapter.scan(data, self.experiment_id)
        
        # Generate sparkline
        sparkline_str = adapter.sparkline(points, width=120)
        ctx.logger.info(f"Entropy sparkline:\n{sparkline_str}")
        
        # Build region findings from entropy points
        findings = []
        regions = []
        
        if points:
            cur_class = adapter.classify_region(points[0].entropy)
            cur_start = points[0].offset
            
            for i in range(1, len(points)):
                cls = adapter.classify_region(points[i].entropy)
                if cls != cur_class:
                    # Region boundary found
                    region = {
                        "start": cur_start,
                        "end": points[i].offset,
                        "size": points[i].offset - cur_start,
                        "class": cur_class,
                        "avg_entropy": sum(p.entropy for p in points if cur_start <= p.offset < points[i].offset) / max(1, len([p for p in points if cur_start <= p.offset < points[i].offset])),
                    }
                    regions.append(region)
                    
                    # Create finding for this region
                    finding = Finding(
                        finding_id=str(uuid.uuid4()),
                        experiment_id=self.experiment_id,
                        kind=FindingKind.REGION,
                        offset=cur_start,
                        size=points[i].offset - cur_start,
                        confidence=ConfidenceLevel.PROBABLE,
                        label=f"Entropy region: {cur_class}",
                        description=f"Entropy class '{cur_class}' from 0x{cur_start:08X} to 0x{points[i].offset:08X} ({points[i].offset - cur_start:,} bytes)",
                        evidence_ids=[e.evidence_id for e in evidences if e.source_offset == points[i].offset],
                        metadata={
                            "entropy_class": cur_class,
                            "avg_entropy": region["avg_entropy"],
                            "window_size": config.window,
                        },
                    )
                    findings.append(finding)
                    
                    cur_class = cls
                    cur_start = points[i].offset
            
            # Final region
            region = {
                "start": cur_start,
                "end": len(data),
                "size": len(data) - cur_start,
                "class": cur_class,
                "avg_entropy": sum(p.entropy for p in points if p.offset >= cur_start) / max(1, len([p for p in points if p.offset >= cur_start])),
            }
            regions.append(region)
            
            finding = Finding(
                finding_id=str(uuid.uuid4()),
                experiment_id=self.experiment_id,
                kind=FindingKind.REGION,
                offset=cur_start,
                size=len(data) - cur_start,
                confidence=ConfidenceLevel.PROBABLE,
                label=f"Entropy region: {cur_class}",
                description=f"Entropy class '{cur_class}' from 0x{cur_start:08X} to end ({len(data) - cur_start:,} bytes)",
                metadata={
                    "entropy_class": cur_class,
                    "avg_entropy": region["avg_entropy"],
                    "window_size": config.window,
                },
            )
            findings.append(finding)
        
        # Write artifacts
        artifacts = {}
        
        if self.parameters.get("output_regions_csv", True) and regions:
            csv_path = ctx.artifacts_dir / "regions.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["start", "end", "size", "class", "avg_entropy"])
                writer.writeheader()
                for r in regions:
                    writer.writerow({**r, "start": f"0x{r['start']:08X}", "end": f"0x{r['end']:08X}"})
            artifacts["regions_csv"] = csv_path
        
        if self.parameters.get("output_sparkline", True):
            sparkline_path = ctx.artifacts_dir / "sparkline.txt"
            sparkline_path.write_text(sparkline_str, encoding="utf-8")
            artifacts["sparkline"] = sparkline_path
        
        # Full entropy points JSON
        points_path = ctx.artifacts_dir / "entropy_points.json"
        points_path.write_text(
            __import__("json").dumps([{"offset": p.offset, "size": getattr(p, "size", config.window), "entropy": p.entropy} for p in points]),
            encoding="utf-8"
        )
        artifacts["entropy_points_json"] = points_path
        
        return ExperimentResult(
            experiment_id=self.experiment_id,
            status="success",
            summary=f"Entropy scan complete: {len(points)} points, {len(regions)} regions, {len(evidences)} evidences",
            findings=findings,
            evidences=evidences,
            artifacts=artifacts,
            metadata={
                "points_analyzed": len(points),
                "regions_found": len(regions),
                "window_size": config.window,
                "step_size": config.step or config.window,
                "file_size": len(data),
            },
        )