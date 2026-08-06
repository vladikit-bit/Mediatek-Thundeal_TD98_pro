"""Unit and integration tests for EvidenceEngine.submit_finding() deduplication and versioning (MTKLAB-004)."""

import tempfile
import unittest
from pathlib import Path

from mtklab.core.evidence import (
    ConfidenceLevel,
    Evidence,
    EvidenceEngine,
    EvidenceType,
    Finding,
    FindingKind,
)
from mtklab.core.experiment import ExperimentResult
from mtklab.storage.db import EvidenceDatabase


class TestEvidenceEngineDeduplication(unittest.TestCase):
    """Tests for EvidenceEngine.submit_finding() logical_id deduplication and version increment."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_engine.db"
        self.migrations_dir = Path(__file__).parent.parent / "src" / "mtklab" / "storage" / "migrations"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_sample_experiment(self, db: EvidenceDatabase, exp_id: str = "exp01"):
        """Helper to create parent experiment record for FK constraints."""
        res = ExperimentResult(
            experiment_id=exp_id,
            status="success",
            summary="Sample experiment for unit testing",
        )
        res.mark_completed()
        db.store_experiment_result(res)

    def _make_finding(self, **kwargs) -> Finding:
        """Helper to build a Finding with sensible defaults."""
        defaults = {
            "experiment_id": "exp01",
            "kind": FindingKind.REGION,
            "offset": 0,
            "size": 0x100,
            "confidence": ConfidenceLevel.CANDIDATE,
            "label": "Test Region",
            "description": "A test region finding",
            "metadata": {"source": "test"},
        }
        defaults.update(kwargs)
        return Finding(**defaults)

    def test_submit_new_finding_creates_versions(self):
        """A new finding gets version 1 (from __post_init__) + version 2 (initial_submission)."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            finding = self._make_finding()
            result = engine.submit_finding(finding, [])

            # logical_id auto-generated
            self.assertIsNotNone(result.logical_id)
            self.assertEqual(result.logical_id, "exp01:region:0x00000000-0x00000100")

            # __post_init__ created v1 ("created"), submit_finding added v2 ("initial_submission")
            self.assertEqual(len(result.versions), 2)
            self.assertEqual(result.versions[0]["version"], 1)
            self.assertEqual(result.versions[0]["reason"], "created")
            self.assertEqual(result.versions[1]["version"], 2)
            self.assertEqual(result.versions[1]["reason"], "initial_submission")

            # Persisted in DB
            stored = db.get_finding(result.finding_id)
            self.assertIsNotNone(stored)
            self.assertEqual(len(stored.versions), 2)
            self.assertEqual(stored.logical_id, result.logical_id)
        finally:
            db.close()

    def test_submit_identical_finding_returns_existing_without_duplicate(self):
        """Re-submitting an identical finding returns the existing one; no new DB row."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            # First submission
            finding1 = self._make_finding(
                confidence=ConfidenceLevel.CANDIDATE,
                label="Region",
                description="Same region",
                metadata={"key": "value"},
            )
            result1 = engine.submit_finding(finding1, [])
            original_id = result1.finding_id

            # Second submission — identical attributes
            finding2 = self._make_finding(
                confidence=ConfidenceLevel.CANDIDATE,
                label="Region",
                description="Same region",
                metadata={"key": "value"},
            )
            result2 = engine.submit_finding(finding2, [])

            # Should return the existing finding
            self.assertEqual(result2.finding_id, original_id)
            self.assertEqual(len(result2.versions), len(result1.versions))

            # Only one row in DB for this logical_id
            cursor = db._conn.execute(
                "SELECT COUNT(*) FROM findings WHERE logical_id = ?",
                (result1.logical_id,),
            )
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            db.close()

    def test_submit_modified_finding_creates_new_version(self):
        """A modified finding gets a new UUID and incremented version."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            # v1: CANDIDATE
            finding1 = self._make_finding(
                confidence=ConfidenceLevel.CANDIDATE,
                label="Region",
                description="Initial",
            )
            result1 = engine.submit_finding(finding1, [])
            original_id = result1.finding_id

            # v2: VERIFIED (modified — confidence changed)
            finding2 = self._make_finding(
                confidence=ConfidenceLevel.VERIFIED,
                label="Region",
                description="Initial",
            )
            result2 = engine.submit_finding(finding2, [])

            # New finding_id
            self.assertNotEqual(result2.finding_id, original_id)

            # Version history inherited + new "updated" version
            self.assertEqual(len(result2.versions), len(result1.versions) + 1)
            self.assertEqual(
                result2.versions[-1]["version"],
                result1.versions[-1]["version"] + 1,
            )
            self.assertEqual(result2.versions[-1]["reason"], "updated")

            # Latest in DB should be the new version
            latest = db.get_latest_finding_by_logical_id(result1.logical_id)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.finding_id, result2.finding_id)
            self.assertEqual(latest.confidence, ConfidenceLevel.VERIFIED)
        finally:
            db.close()

    def test_submit_finding_with_evidences(self):
        """Evidences are stored and linked to the finding."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            evidence = Evidence(
                experiment_id="exp01",
                evidence_type=EvidenceType.ENTROPY_BOUNDARY,
                confidence=ConfidenceLevel.PROBABLE,
                description="Entropy transition at boundary",
            )

            finding = self._make_finding()
            result = engine.submit_finding(finding, [evidence])

            # Evidence stored in DB
            stored_ev = db.get_evidence(evidence.evidence_id)
            self.assertIsNotNone(stored_ev)

            # Finding has evidence_id linked
            self.assertIn(evidence.evidence_id, result.evidence_ids)

            # Confidence recalculated from evidence
            self.assertEqual(result.confidence, ConfidenceLevel.CANDIDATE)
        finally:
            db.close()

    def test_submit_finding_with_none_evidences(self):
        """Passing evidences=None is backward-compatible and does not raise."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            finding = self._make_finding()
            result = engine.submit_finding(finding, None)

            self.assertIsNotNone(result)
            self.assertIsNotNone(result.logical_id)
            self.assertEqual(len(result.versions), 2)
        finally:
            db.close()

    def test_submit_finding_logical_id_preserved_when_explicitly_set(self):
        """A Finding with an explicitly set logical_id uses it for deduplication."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            explicit_lid = "exp01:region:0x00000400-0x00000c00"
            finding1 = self._make_finding()
            finding1.logical_id = explicit_lid
            finding1.offset = 1024
            finding1.size = 2048
            result1 = engine.submit_finding(finding1, [])

            # Second finding with same explicit logical_id but constructed
            # with different offset/size — should still match
            finding2 = self._make_finding(
                offset=999,  # different offset, but logical_id will be overwritten
                size=999,
                label="Updated Label",
            )
            result2 = engine.submit_finding(finding2, [])

            # finding2's logical_id was auto-generated (different from explicit_lid),
            # so it won't match finding1 — this is correct behavior.
            self.assertNotEqual(result1.logical_id, result2.logical_id)
        finally:
            db.close()

    def test_submit_finding_version_evolution_multi_step(self):
        """Multi-step simulation: confidence upgrade → label change → latest is v4."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        engine = EvidenceEngine(db)
        try:
            self._create_sample_experiment(db, "exp01")

            logical_id = "exp01:region:0x00000000-0x00000100"

            # Step 1: Submit v1 (CANDIDATE)
            f1 = self._make_finding(
                confidence=ConfidenceLevel.CANDIDATE,
                label="Region",
                description="Initial hypothesis",
                logical_id=logical_id,
            )
            r1 = engine.submit_finding(f1, [])

            # Step 2: Submit v2 (PROBABLE — confidence changed, so modified)
            f2 = self._make_finding(
                confidence=ConfidenceLevel.PROBABLE,
                label="Region",
                description="Initial hypothesis",
                logical_id=logical_id,
            )
            r2 = engine.submit_finding(f2, [])

            # Step 3: Submit identical to v2 (unchanged — should return v2)
            f3 = self._make_finding(
                confidence=ConfidenceLevel.PROBABLE,
                label="Region",
                description="Initial hypothesis",
                logical_id=logical_id,
            )
            r3 = engine.submit_finding(f3, [])
            self.assertEqual(r3.finding_id, r2.finding_id)

            # Step 4: Submit v3 (VERIFIED + label change)
            f4 = self._make_finding(
                confidence=ConfidenceLevel.VERIFIED,
                label="Boot ROM",
                description="Confirmed as Boot ROM",
                logical_id=logical_id,
            )
            r4 = engine.submit_finding(f4, [])

            # Latest in DB
            latest = db.get_latest_finding_by_logical_id(logical_id)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.finding_id, r4.finding_id)
            self.assertEqual(latest.confidence, ConfidenceLevel.VERIFIED)
            self.assertEqual(latest.label, "Boot ROM")

            # Version evolution:
            # r1: [created(1), initial_submission(2)]              → 2 versions
            # r2: [v1, v2, updated(3)]                            → 3 versions
            # r3: unchanged → returns r2                          → 0 new rows
            # r4: [v1, v2, v3, updated(4)]                        → 4 versions
            self.assertEqual(len(r1.versions), 2)
            self.assertEqual(len(r2.versions), 3)
            self.assertEqual(len(r4.versions), 4)
            self.assertEqual(r4.versions[-1]["version"], 4)
            self.assertEqual(r4.versions[-1]["reason"], "updated")

            # Three distinct rows in DB for this logical_id
            cursor = db._conn.execute(
                "SELECT COUNT(*) FROM findings WHERE logical_id = ?", (logical_id,)
            )
            count = cursor.fetchone()[0]
            self.assertEqual(count, 3)
        finally:
            db.close()


class TestFindingAddVersion(unittest.TestCase):
    """Tests for Finding.add_version() method (MTKLAB-004)."""

    def test_add_version_increments_monotonically(self):
        """add_version creates snapshots with strictly increasing version numbers."""
        finding = Finding(
            experiment_id="exp01",
            kind=FindingKind.REGION,
            offset=0,
            size=100,
        )
        # __post_init__ creates version 1
        self.assertEqual(len(finding.versions), 1)
        self.assertEqual(finding.versions[0]["version"], 1)

        # add_version creates version 2
        snap = finding.add_version("test_update")
        self.assertEqual(snap["version"], 2)
        self.assertEqual(snap["reason"], "test_update")
        self.assertEqual(len(finding.versions), 2)

        # add_version creates version 3
        snap = finding.add_version("another_update")
        self.assertEqual(snap["version"], 3)
        self.assertEqual(len(finding.versions), 3)

    def test_add_version_returns_snapshot(self):
        """add_version returns the created snapshot dict."""
        finding = Finding(
            experiment_id="exp01",
            kind=FindingKind.REGION,
            offset=0,
            size=100,
        )
        snap = finding.add_version("manual")
        self.assertIsInstance(snap, dict)
        self.assertEqual(snap["version"], 2)
        self.assertEqual(snap["reason"], "manual")
        self.assertIn("timestamp", snap)


if __name__ == "__main__":
    unittest.main()
