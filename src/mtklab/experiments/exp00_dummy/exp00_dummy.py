"""Exp00 Dummy - Infrastructure test experiment."""

import time
import uuid
from pathlib import Path

from mtklab.experiments import Experiment, ExperimentContext, ExperimentResult
from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind


class Exp00Dummy(Experiment):
    """No-op experiment to verify CLI → Registry → Context → DB pipeline."""
    
    experiment_id = "exp00_dummy"
    display_name = "Dummy Experiment (Infrastructure Test)"
    description = "No-op experiment to verify CLI → Registry → Context → DB pipeline"
    version = "1.0.0"
    requires = []
    parameters = {
        "sleep_seconds": 0.1,
        "create_finding": True,
    }
    
    def run(self, ctx: ExperimentContext) -> ExperimentResult:
        # Simulate some work
        time.sleep(self.parameters.get("sleep_seconds", 0.1))
        
        findings = []
        evidences = []
        
        if self.parameters.get("create_finding", True):
            # Create a test finding
            finding = Finding(
                finding_id=str(uuid.uuid4()),
                experiment_id=self.experiment_id,
                kind=FindingKind.REGION,
                offset=0,
                size=100,
                confidence=ConfidenceLevel.CANDIDATE,
                label="Test Region",
                description="Dummy finding created by exp00_dummy",
                metadata={"source": "exp00_dummy", "test": True},
            )
            findings.append(finding)
            
            # Create supporting evidence
            evidence = Evidence(
                experiment_id=self.experiment_id,
                evidence_type=EvidenceType.MANUAL_ANNOTATION,
                confidence=ConfidenceLevel.CANDIDATE,
                description="Test evidence for dummy finding",
                data={"test": True},
                source_offset=0,
                source_size=100,
                tags=["test", "dummy"],
            )
            evidences.append(evidence)
        
        # Create a test artifact
        artifact_path = ctx.artifacts_dir / "exp00_dummy.json"
        artifact_path.write_text('{"test": true, "experiment": "exp00_dummy"}', encoding="utf-8")
        
        return ExperimentResult(
            experiment_id=self.experiment_id,
            status="success",
            summary=f"Dummy experiment completed. Created {len(findings)} finding(s).",
            findings=findings,
            evidences=evidences,
            artifacts={"test_json": artifact_path},
            metadata={"sleep_seconds": self.parameters.get("sleep_seconds", 0.1)},
        )