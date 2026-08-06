import sys
import shutil
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mtklab.core import Project, Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind
from mtklab.core.hypothesis import Hypothesis, HypothesisStatus

def main():
    test_dir = Path("data/projects/test_project")
    if test_dir.exists():
        shutil.rmtree(test_dir)
        
    print("1. Creating Project session...")
    proj = Project("test_project")
    
    # Check migrations applied
    cursor = proj.db._conn.execute("SELECT version FROM schema_migrations")
    versions = [r[0] for r in cursor.fetchall()]
    assert versions == [1, 2], f"Expected version [1, 2], got {versions}"
    print(" - Migrations applied successfully.")

    print("2. Testing Evidence API...")
    from mtklab.core.experiment import ExperimentResult
    res = ExperimentResult(experiment_id="exp_test", status="success", summary="Test experiment")
    res.mark_completed()
    proj.db.store_experiment_result(res)

    ev = Evidence(
        experiment_id="exp_test",
        evidence_type=EvidenceType.SIGNATURE_MATCH,
        confidence=ConfidenceLevel.CANDIDATE,
        description="Test evidence",
        data={"key": "value"},
        source_offset=123,
        tags=["test"]
    )
    proj.db.store_evidence(ev)
    ev_ret = proj.db.get_evidence(ev.evidence_id)
    assert ev_ret is not None
    assert ev_ret.description == "Test evidence"
    assert ev_ret.data == {"key": "value"}
    print(" - Evidence stored and retrieved successfully.")

    print("3. Testing Finding API (with versioning JSON)...")
    fnd = Finding(
        experiment_id="exp_test",
        kind=FindingKind.REGION,
        offset=100,
        size=500,
        confidence=ConfidenceLevel.CANDIDATE,
        description="A test finding",
    )
    # Finding auto-generates one version snapshot on init
    assert len(fnd.versions) == 1
    proj.db.store_finding(fnd)
    
    # Update finding
    fnd.upgrade_confidence(ConfidenceLevel.PROBABLE, "More evidence found")
    assert len(fnd.versions) == 2
    proj.db.update_finding(fnd)
    
    fnd_ret = proj.db.get_finding(fnd.finding_id)
    assert fnd_ret.confidence == ConfidenceLevel.PROBABLE
    assert len(fnd_ret.versions) == 2
    assert fnd_ret.versions[-1]["reason"].startswith("upgrade: More evidence")
    print(" - Finding stored, updated, and versioning preserved.")

    print("4. Testing Hypothesis API...")
    hyp = Hypothesis(
        subject_offset=100,
        subject_size=500,
        claim="It's a region"
    )
    proj.db.store_hypothesis(hyp)
    hyp_list = proj.db.get_hypotheses_for_offset(150, None)
    assert len(hyp_list) == 1
    assert hyp_list[0].claim == "It's a region"
    print(" - Hypothesis stored and retrieved successfully.")

    print("5. Testing Artifact Manager...")
    csv_path = proj.artifacts.store_csv("exp_test", "results.csv", [{"a": 1, "b": 2}])
    assert csv_path.exists()
    assert csv_path.parent.name == "exp_test"
    json_path = proj.artifacts.store_json("exp_test", "stats.json", {"count": 1})
    assert json_path.exists()
    
    # Artifact Database References
    ref_id = proj.db.store_artifact_reference("exp_test", "results", csv_path, "Test CSV")
    refs = proj.db.get_experiment_artifacts("exp_test")
    assert "results" in refs
    print(" - Artifact stored and DB reference created.")

    proj.close()
    print("All tests passed.")

if __name__ == "__main__":
    main()
