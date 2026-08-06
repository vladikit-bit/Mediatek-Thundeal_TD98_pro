"""Migration, foreign key enforcement, and storage tests for EvidenceDatabase."""

import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

from mtklab.core.evidence import ConfidenceLevel, Evidence, EvidenceType, Finding, FindingKind
from mtklab.core.experiment import ExperimentResult
from mtklab.core.hypothesis import Hypothesis, HypothesisStatus
from mtklab.storage.db import EvidenceDatabase
from mtklab.storage.migrations import MigrationManager


class TestStorageMigrationsAndOperations(unittest.TestCase):
    """Test schema migration 002_logical_ids and EvidenceDatabase operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_evidence.db"
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

    def test_migration_002_applies_correctly_on_v1_database(self):
        """Verify applying 002_logical_ids.sql on a v1 database adds logical_id column and index."""
        conn = sqlite3.connect(str(self.db_path))

        # Apply only 001_initial.sql
        initial_sql_path = self.migrations_dir / "001_initial.sql"
        conn.executescript(initial_sql_path.read_text(encoding="utf-8"))
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, filename TEXT, applied_at TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO schema_migrations (version, filename) VALUES (1, '001_initial.sql')"
        )
        conn.commit()

        # Insert a sample experiment record first for FK safety
        conn.execute(
            """
            INSERT INTO experiments (
                experiment_id, display_name, version, status, started_at, summary, parameters_json, metadata_json, errors_json
            ) VALUES ('exp01', 'Exp 01', '1.0.0', 'success', '2026-01-01T00:00:00', 'Summary', '{}', '{}', '[]')
            """
        )

        # Insert a sample finding into v1 database
        conn.execute(
            """
            INSERT INTO findings (
                finding_id, experiment_id, kind, offset, size,
                confidence, label, description, evidence_ids_json,
                metadata_json, versions_json
            ) VALUES ('f1', 'exp01', 'region', 0, 100, 'CANDIDATE', 'L1', 'Desc', '[]', '{}', '[]')
            """
        )
        conn.commit()

        # Run MigrationManager to apply 002 migration
        migrator = MigrationManager(conn, self.migrations_dir)
        migrator.apply_migrations()

        # Check applied migrations
        cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        versions = [row[0] for row in cursor.fetchall()]
        self.assertEqual(versions, [1, 2])

        # Verify logical_id column exists
        cursor = conn.execute("PRAGMA table_info(findings)")
        columns = [row[1] for row in cursor.fetchall()]
        self.assertIn("logical_id", columns)

        # Verify index exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_findings_logical_id'")
        idx_row = cursor.fetchone()
        self.assertIsNotNone(idx_row)

        # Query existing finding inserted before migration
        cursor = conn.execute("SELECT finding_id, logical_id FROM findings WHERE finding_id = 'f1'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "f1")
        self.assertIsNone(row[1])

        conn.close()

    def test_foreign_key_enforcement(self):
        """Test that PRAGMA foreign_keys = ON is enforced and prevents orphans without parent experiment."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            # 1. Attempting to insert finding with non-existent experiment_id should fail
            orphan_finding = Finding(
                experiment_id="nonexistent_exp",
                kind=FindingKind.REGION,
                offset=0,
                size=10,
                confidence=ConfidenceLevel.CANDIDATE,
                description="Orphan finding",
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.store_finding(orphan_finding)

            # 2. Attempting to insert evidence with non-existent experiment_id should fail
            orphan_evidence = Evidence(
                evidence_id="ev_orphan",
                experiment_id="nonexistent_exp",
                evidence_type=EvidenceType.SIGNATURE_MATCH,
                confidence=ConfidenceLevel.PROBABLE,
                description="Orphan evidence",
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.store_evidence(orphan_evidence)

            # 3. When parent experiment exists, storage succeeds
            self._create_sample_experiment(db, "valid_exp")
            valid_finding = Finding(
                experiment_id="valid_exp",
                kind=FindingKind.REGION,
                offset=0,
                size=10,
                confidence=ConfidenceLevel.CANDIDATE,
                description="Valid finding",
            )
            db.store_finding(valid_finding)
            retrieved = db.get_finding(valid_finding.finding_id)
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.finding_id, valid_finding.finding_id)
        finally:
            db.close()

    def test_store_and_get_finding_with_logical_id(self):
        """Integration test: store_finding persists and retrieves logical_id."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")

            finding = Finding(
                experiment_id="exp01",
                kind=FindingKind.HEADER,
                offset=0,
                size=64,
                confidence=ConfidenceLevel.VERIFIED,
                label="Boot Header",
                description="Identified boot header",
                logical_id="exp01:header:0x00000000-0x00000040",
            )
            db.store_finding(finding)

            retrieved = db.get_finding(finding.finding_id)
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.logical_id, "exp01:header:0x00000000-0x00000040")
            self.assertEqual(retrieved.finding_id, finding.finding_id)
            self.assertEqual(retrieved.confidence, ConfidenceLevel.VERIFIED)

            # Test a legacy-style finding that genuinely has no logical_id,
            # e.g. a pre-MTKLAB-002 record. Since MTKLAB-002, constructing a
            # Finding without logical_id auto-generates one (see
            # test_evidence.py::test_finding_auto_generates_logical_id_when_omitted),
            # so a NULL value is forced onto the object *after* construction
            # here to simulate that legacy case and verify the storage layer
            # still round-trips a genuine NULL without corrupting it.
            finding_no_id = Finding(
                experiment_id="exp01",
                kind=FindingKind.STREAM,
                offset=100,
                size=200,
                confidence=ConfidenceLevel.CANDIDATE,
                description="Stream finding",
            )
            finding_no_id.logical_id = None
            db.store_finding(finding_no_id)

            retrieved_no_id = db.get_finding(finding_no_id.finding_id)
            self.assertIsNotNone(retrieved_no_id)
            self.assertIsNone(retrieved_no_id.logical_id)
        finally:
            db.close()

    def test_store_evidence_insert_or_ignore(self):
        """Test store_evidence handles duplicate evidence_id safely using INSERT OR IGNORE."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")

            ev = Evidence(
                evidence_id="ev1",
                experiment_id="exp01",
                evidence_type=EvidenceType.SIGNATURE_MATCH,
                confidence=ConfidenceLevel.PROBABLE,
                description="Sig match",
            )
            db.store_evidence(ev)

            # Insert identical evidence again - should be ignored without raising Primary Key error
            db.store_evidence(ev)

            retrieved = db.get_evidence("ev1")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.evidence_id, "ev1")
        finally:
            db.close()

    def test_store_finding_insert_or_ignore(self):
        """Test store_finding handles duplicate finding_id safely using INSERT OR IGNORE."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")

            f = Finding(
                finding_id="f_dup_test",
                experiment_id="exp01",
                kind=FindingKind.HEADER,
                offset=0,
                size=128,
                confidence=ConfidenceLevel.PROBABLE,
                label="Original Label",
                description="Original description",
            )
            db.store_finding(f)

            # Try storing a duplicate finding with same ID but different label via store_finding
            f_dup = Finding(
                finding_id="f_dup_test",
                experiment_id="exp01",
                kind=FindingKind.HEADER,
                offset=0,
                size=128,
                confidence=ConfidenceLevel.VERIFIED,
                label="Duplicate Overwrite Attempt",
                description="New description",
            )
            db.store_finding(f_dup)

            retrieved = db.get_finding("f_dup_test")
            self.assertIsNotNone(retrieved)
            # Should preserve original record because INSERT OR IGNORE ignored duplicate
            self.assertEqual(retrieved.label, "Original Label")
            self.assertEqual(retrieved.confidence, ConfidenceLevel.PROBABLE)
        finally:
            db.close()

    def test_store_hypothesis_insert_or_ignore(self):
        """Test store_hypothesis handles duplicate hypothesis_id safely using INSERT OR IGNORE."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            hyp = Hypothesis(
                hypothesis_id="h_dup_test",
                subject_offset=100,
                subject_size=200,
                claim="Original claim",
            )
            db.store_hypothesis(hyp)

            hyp_dup = Hypothesis(
                hypothesis_id="h_dup_test",
                subject_offset=100,
                subject_size=200,
                claim="Modified claim attempt",
            )
            db.store_hypothesis(hyp_dup)

            hypotheses = db.get_hypotheses_for_offset(150)
            self.assertEqual(len(hypotheses), 1)
            self.assertEqual(hypotheses[0].claim, "Original claim")
        finally:
            db.close()

    # --- MTKLAB-003: get_latest_finding_by_logical_id tests ---

    def _make_versioned_finding(
        self,
        db: EvidenceDatabase,
        exp_id: str,
        logical_id: str,
        version_num: int,
        confidence: ConfidenceLevel,
        label: str,
        description: str,
    ) -> Finding:
        """Helper: build a Finding with a specific version snapshot and store it.

        Simulates what EvidenceEngine.submit_finding (MTKLAB-004) will produce:
        each version snapshot gets its own finding_id UUID while sharing logical_id.
        """
        finding = Finding(
            finding_id=str(uuid.uuid4()),
            experiment_id=exp_id,
            kind=FindingKind.REGION,
            offset=0,
            size=0x100,
            confidence=confidence,
            label=label,
            description=description,
            logical_id=logical_id,
        )
        # Replace the auto-created "created" snapshot with a version history
        # that ends at version_num.
        finding.versions = [
            {
                "version": v,
                "confidence": finding.confidence.name,
                "label": finding.label,
                "description": finding.description,
                "evidence_ids": list(finding.evidence_ids),
                "metadata": dict(finding.metadata),
                "reason": f"version_{v}_snapshot",
                "timestamp": datetime.utcnow().isoformat(),
            }
            for v in range(1, version_num + 1)
        ]
        db.store_finding(finding)
        return finding

    def test_get_latest_finding_by_logical_id_no_match(self):
        """Querying a non-existent logical_id returns None."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")
            result = db.get_latest_finding_by_logical_id("nonexistent:region:0x00000000-0x00000100")
            self.assertIsNone(result)
        finally:
            db.close()

    def test_get_latest_finding_by_logical_id_single_version(self):
        """A finding with a single version (v1) is returned correctly."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")
            logical_id = "exp01:region:0x00000000-0x00000100"

            stored = self._make_versioned_finding(
                db, "exp01", logical_id, version_num=1,
                confidence=ConfidenceLevel.CANDIDATE,
                label="Initial", description="First version",
            )
            db.store_finding(stored)

            result = db.get_latest_finding_by_logical_id(logical_id)
            self.assertIsNotNone(result)
            self.assertEqual(result.logical_id, logical_id)
            self.assertEqual(result.finding_id, stored.finding_id)
            # The versions list should contain the single snapshot
            self.assertEqual(len(result.versions), 1)
            self.assertEqual(result.versions[0]["version"], 1)
        finally:
            db.close()

    def test_get_latest_finding_by_logical_id_multiple_versions(self):
        """Among multiple rows sharing the same logical_id, the highest version is returned."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")
            logical_id = "exp01:region:0x00000400-0x00000800"

            # Store version 1 (lower confidence)
            v1 = self._make_versioned_finding(
                db, "exp01", logical_id, version_num=1,
                confidence=ConfidenceLevel.CANDIDATE,
                label="Candidate", description="Initial hypothesis",
            )
            db.store_finding(v1)

            # Store version 2 (higher confidence — finding was refined)
            v2 = self._make_versioned_finding(
                db, "exp01", logical_id, version_num=2,
                confidence=ConfidenceLevel.VERIFIED,
                label="Verified Region", description="Confirmed via CRC",
            )
            db.store_finding(v2)

            # Store version 3 (modified again)
            v3 = self._make_versioned_finding(
                db, "exp01", logical_id, version_num=3,
                confidence=ConfidenceLevel.VERIFIED,
                label="Boot ROM", description="Identified as Boot ROM region",
            )
            db.store_finding(v3)

            result = db.get_latest_finding_by_logical_id(logical_id)
            self.assertIsNotNone(result)
            self.assertEqual(result.logical_id, logical_id)
            self.assertEqual(result.finding_id, v3.finding_id)
            self.assertEqual(result.confidence, ConfidenceLevel.VERIFIED)
            self.assertEqual(result.label, "Boot ROM")
            self.assertEqual(result.versions[-1]["version"], 3)
            self.assertEqual(len(result.versions), 3)
        finally:
            db.close()

    def test_get_latest_finding_by_logical_id_null_not_matched(self):
        """Findings with NULL logical_id are never returned by logical_id lookup."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")

            # A legacy finding with NULL logical_id
            legacy = Finding(
                finding_id=str(uuid.uuid4()),
                experiment_id="exp01",
                kind=FindingKind.STREAM,
                offset=100,
                size=500,
                confidence=ConfidenceLevel.CANDIDATE,
                description="Legacy finding without logical_id",
            )
            legacy.logical_id = None
            db.store_finding(legacy)

            # Querying for any logical_id should not return the NULL row
            result = db.get_latest_finding_by_logical_id("exp01:stream:0x00000064-0x000002bc")
            self.assertIsNone(result)
        finally:
            db.close()

    def test_get_latest_finding_by_logical_id_distinct_ids(self):
        """Multiple logical_ids are kept separate; each returns its own latest."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")
            lid_a = "exp01:region:0x00000000-0x00000100"
            lid_b = "exp01:region:0x00001000-0x00002000"

            a1 = self._make_versioned_finding(
                db, "exp01", lid_a, version_num=1,
                confidence=ConfidenceLevel.CANDIDATE,
                label="A v1", description="A first",
            )
            a2 = self._make_versioned_finding(
                db, "exp01", lid_a, version_num=2,
                confidence=ConfidenceLevel.PROBABLE,
                label="A v2", description="A second",
            )
            b1 = self._make_versioned_finding(
                db, "exp01", lid_b, version_num=1,
                confidence=ConfidenceLevel.CANDIDATE,
                label="B v1", description="B first",
            )
            db.store_finding(a1)
            db.store_finding(a2)
            db.store_finding(b1)

            result_a = db.get_latest_finding_by_logical_id(lid_a)
            self.assertIsNotNone(result_a)
            self.assertEqual(result_a.finding_id, a2.finding_id)
            self.assertEqual(result_a.versions[-1]["version"], 2)

            result_b = db.get_latest_finding_by_logical_id(lid_b)
            self.assertIsNotNone(result_b)
            self.assertEqual(result_b.finding_id, b1.finding_id)
            self.assertEqual(result_b.versions[-1]["version"], 1)
        finally:
            db.close()

    def test_get_findings_with_null_logical_id_does_not_crash(self):
        """Querying for a logical_id when the table has NULL logical_id rows
        (legacy) does not raise and correctly returns only matching rows."""
        db = EvidenceDatabase(self.db_path, self.migrations_dir)
        try:
            self._create_sample_experiment(db, "exp01")

            # Legacy finding with NULL logical_id
            legacy = Finding(
                finding_id=str(uuid.uuid4()),
                experiment_id="exp01",
                kind=FindingKind.UNKNOWN,
                offset=0,
                size=10,
                confidence=ConfidenceLevel.CANDIDATE,
                description="Legacy NULL logical_id finding",
            )
            legacy.logical_id = None
            db.store_finding(legacy)

            # Modern finding with a real logical_id
            modern = self._make_versioned_finding(
                db, "exp01", "exp01:unknown:0x00000000-0x0000000a", version_num=1,
                confidence=ConfidenceLevel.PROBABLE,
                label="Modern", description="Has logical_id",
            )
            db.store_finding(modern)

            result = db.get_latest_finding_by_logical_id("exp01:unknown:0x00000000-0x0000000a")
            self.assertIsNotNone(result)
            self.assertEqual(result.finding_id, modern.finding_id)
            self.assertIsNotNone(result.logical_id)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

