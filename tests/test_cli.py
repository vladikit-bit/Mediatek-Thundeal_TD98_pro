"""Integration tests for the CLI (MTKLAB-010 run tracking, MTKLAB-011
status/inspect enhancements), using Click's real CliRunner against an
isolated filesystem so nothing touches the actual data/projects directory."""

import json
import sqlite3
import unittest

from click.testing import CliRunner

from mtklab.cli import cli


class TestExperimentParametersProvenance(unittest.TestCase):
    """Regression tests for a confirmed provenance bug found during
    architecture review: db.py's store_experiment_result() has always
    written json.dumps(getattr(result, "parameters", {})) into the
    experiments table's parameters_json column, but ExperimentResult never
    actually had a `parameters` attribute -- so that column was empty for
    every experiment run in the project's history. Fixed by adding the
    field to ExperimentResult and having cli.py's `run` command populate
    it uniformly from exp.parameters after every return path.

    Known limitation (documented, not fixed here): the experiments table
    is keyed by experiment_id and overwritten each run, so this reflects
    only the most recent run's parameters, not necessarily the exact
    parameters active when a specific already-persisted Finding/Evidence
    was originally created. True per-observation provenance would need a
    parameters column on the per-invocation experiment_runs table instead.
    """

    def setUp(self):
        self.runner = CliRunner()

    def _query_parameters(self, db_path: str, experiment_id: str) -> dict:
        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT parameters_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        conn.close()
        return json.loads(row[0])

    def test_successful_run_captures_actual_parameters(self):
        with self.runner.isolated_filesystem():
            self.runner.invoke(cli, ["init-project", "proj"])
            result = self.runner.invoke(cli, ["run", "--project", "proj", "exp00_dummy"])
            self.assertEqual(result.exit_code, 0, result.output)

            params = self._query_parameters("data/projects/proj/evidence.db", "exp00_dummy")
            # Must be the REAL parameters dict, not the old always-empty {}.
            self.assertNotEqual(params, {})
            self.assertIn("sleep_seconds", params)
            self.assertIn("create_finding", params)

    def test_clean_failure_path_also_captures_parameters(self):
        """The 'failed' ExperimentResult returned without raising (e.g.
        exp01's 'REE payload not found') must also get parameters -- not
        just the success path."""
        with self.runner.isolated_filesystem():
            self.runner.invoke(cli, ["init-project", "proj"])
            result = self.runner.invoke(cli, ["run", "--project", "proj", "exp01_entropy_landscape"])
            self.assertEqual(result.exit_code, 0, result.output)

            params = self._query_parameters("data/projects/proj/evidence.db", "exp01_entropy_landscape")
            self.assertNotEqual(params, {})

    def test_raised_exception_path_also_captures_parameters(self):
        import mtklab.experiments.exp00_dummy.exp00_dummy as exp00_mod

        def boom(self, ctx):
            raise RuntimeError("synthetic failure")

        original_run = exp00_mod.Exp00Dummy.run
        exp00_mod.Exp00Dummy.run = boom
        try:
            with self.runner.isolated_filesystem():
                self.runner.invoke(cli, ["init-project", "proj"])
                result = self.runner.invoke(cli, ["run", "--project", "proj", "exp00_dummy"])
                self.assertEqual(result.exit_code, 0, result.output)

                params = self._query_parameters("data/projects/proj/evidence.db", "exp00_dummy")
                self.assertNotEqual(params, {})
                self.assertIn("sleep_seconds", params)
        finally:
            exp00_mod.Exp00Dummy.run = original_run


class TestCLIRunTracking(unittest.TestCase):
    """MTKLAB-010: `mtklab run` creates runs/experiment_runs records."""

    def setUp(self):
        self.runner = CliRunner()

    def _init_project(self, name="proj"):
        result = self.runner.invoke(cli, ["init-project", name])
        self.assertEqual(result.exit_code, 0, result.output)

    def _query(self, db_path, sql, params=()):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def test_run_creates_run_and_experiment_run_records(self):
        with self.runner.isolated_filesystem():
            self._init_project("proj")
            result = self.runner.invoke(cli, ["run", "--project", "proj", "exp00_dummy"])
            self.assertEqual(result.exit_code, 0, result.output)

            db_path = "data/projects/proj/evidence.db"
            runs = self._query(db_path, "SELECT * FROM runs")
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["project_id"], "proj")

            exp_runs = self._query(db_path, "SELECT * FROM experiment_runs")
            self.assertEqual(len(exp_runs), 1)
            self.assertEqual(exp_runs[0]["experiment_id"], "exp00_dummy")
            self.assertEqual(exp_runs[0]["status"], "SUCCESS")
            self.assertIsNotNone(exp_runs[0]["duration_seconds"])
            self.assertEqual(exp_runs[0]["run_id"], runs[0]["run_id"])

    def test_run_clean_failure_records_status_and_error_message(self):
        """A "failed" ExperimentResult returned WITHOUT raising (e.g.
        exp01's "REE payload not found") must still populate
        error_message, not just status -- this does not go through the
        `except Exception` branch at all."""
        with self.runner.isolated_filesystem():
            self._init_project("proj")
            result = self.runner.invoke(cli, ["run", "--project", "proj", "exp01_entropy_landscape"])
            self.assertEqual(result.exit_code, 0, result.output)

            db_path = "data/projects/proj/evidence.db"
            exp_runs = self._query(db_path, "SELECT * FROM experiment_runs")
            self.assertEqual(len(exp_runs), 1)
            self.assertEqual(exp_runs[0]["status"], "FAILED")
            self.assertIsNotNone(exp_runs[0]["error_message"])
            self.assertIn("not found", exp_runs[0]["error_message"])

    def test_run_raised_exception_records_failed_with_error_message(self):
        """The `except Exception` branch: an experiment that genuinely
        raises must also be recorded as FAILED with the exception message."""
        with self.runner.isolated_filesystem():
            self._init_project("proj")

            import mtklab.experiments.exp00_dummy.exp00_dummy as exp00_mod

            original_run = exp00_mod.Exp00Dummy.run

            def boom(self, ctx):
                raise RuntimeError("synthetic failure for testing")

            exp00_mod.Exp00Dummy.run = boom
            try:
                result = self.runner.invoke(cli, ["run", "--project", "proj", "exp00_dummy"])
            finally:
                exp00_mod.Exp00Dummy.run = original_run

            self.assertEqual(result.exit_code, 0, result.output)
            db_path = "data/projects/proj/evidence.db"
            exp_runs = self._query(db_path, "SELECT * FROM experiment_runs")
            self.assertEqual(exp_runs[0]["status"], "FAILED")
            self.assertIn("synthetic failure", exp_runs[0]["error_message"])

    def test_run_id_is_shared_across_multiple_experiments_in_one_run(self):
        with self.runner.isolated_filesystem():
            self._init_project("proj")
            result = self.runner.invoke(
                cli, ["run", "--project", "proj", "exp00_dummy", "exp01_entropy_landscape"]
            )
            self.assertEqual(result.exit_code, 0, result.output)

            db_path = "data/projects/proj/evidence.db"
            runs = self._query(db_path, "SELECT * FROM runs")
            exp_runs = self._query(db_path, "SELECT * FROM experiment_runs")
            self.assertEqual(len(runs), 1)
            self.assertEqual(len(exp_runs), 2)
            self.assertTrue(all(er["run_id"] == runs[0]["run_id"] for er in exp_runs))

    def test_dry_run_creates_no_run_records(self):
        """--dry-run must not create a runs row at all (nothing executes)."""
        with self.runner.isolated_filesystem():
            self._init_project("proj")
            result = self.runner.invoke(cli, ["run", "--project", "proj", "--all", "--dry-run"])
            self.assertEqual(result.exit_code, 0, result.output)
            db_path = "data/projects/proj/evidence.db"
            self.assertEqual(self._query(db_path, "SELECT * FROM runs"), [])


class TestCLIStatusAndInspect(unittest.TestCase):
    """MTKLAB-011: `mtklab status` / `mtklab inspect` enhancements."""

    def setUp(self):
        self.runner = CliRunner()

    def _init_and_run(self, project="proj", *experiment_ids):
        self.runner.invoke(cli, ["init-project", project])
        return self.runner.invoke(cli, ["run", "--project", project, *experiment_ids])

    def test_status_shows_run_count_and_logical_id_count_on_empty_project(self):
        """Edge case (sec. 8): zero runs / zero findings must render
        cleanly, no traceback."""
        with self.runner.isolated_filesystem():
            self.runner.invoke(cli, ["init-project", "proj"])
            result = self.runner.invoke(cli, ["status", "--project", "proj"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Runs:", result.output)
            self.assertIn("0 total", result.output)

    def test_status_after_run_shows_nonzero_counts(self):
        with self.runner.isolated_filesystem():
            run_result = self._init_and_run("proj", "exp00_dummy")
            self.assertEqual(run_result.exit_code, 0, run_result.output)

            result = self.runner.invoke(cli, ["status", "--project", "proj"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Runs:", result.output)
            self.assertIn("1 total", result.output)
            self.assertIn("unique logical_id", result.output)
            self.assertIn("CANDIDATE", result.output)

    def test_inspect_by_experiment_id_still_works_unchanged(self):
        """Backward compatibility: inspect <experiment_id> keeps showing
        the experiment JSON exactly as before MTKLAB-011."""
        with self.runner.isolated_filesystem():
            run_result = self._init_and_run("proj", "exp00_dummy")
            self.assertEqual(run_result.exit_code, 0, run_result.output)

            result = self.runner.invoke(cli, ["inspect", "--project", "proj", "exp00_dummy"])
            self.assertEqual(result.exit_code, 0, result.output)
            payload = json.loads(result.output)
            self.assertEqual(payload["experiment_id"], "exp00_dummy")
            self.assertIn("findings", payload)

    def test_inspect_by_logical_id_shows_version_history_and_evidence(self):
        with self.runner.isolated_filesystem():
            run_result = self._init_and_run("proj", "exp00_dummy")
            self.assertEqual(run_result.exit_code, 0, run_result.output)

            db_path = "data/projects/proj/evidence.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            logical_id = conn.execute(
                "SELECT logical_id FROM findings WHERE logical_id IS NOT NULL LIMIT 1"
            ).fetchone()["logical_id"]
            conn.close()
            self.assertIsNotNone(logical_id)

            result = self.runner.invoke(cli, ["inspect", "--project", "proj", logical_id])
            self.assertEqual(result.exit_code, 0, result.output)
            payload = json.loads(result.output)
            self.assertEqual(payload["logical_id"], logical_id)
            self.assertIn("versions", payload)
            self.assertIn("evidence", payload)
            self.assertGreater(len(payload["versions"]), 0)

    def test_inspect_nonexistent_identifier_exits_1_with_clear_message(self):
        with self.runner.isolated_filesystem():
            self.runner.invoke(cli, ["init-project", "proj"])
            result = self.runner.invoke(cli, ["inspect", "--project", "proj", "does-not-exist-anywhere"])
            self.assertEqual(result.exit_code, 1)
            self.assertIn("No experiment, logical_id, or finding_id", result.output)


class TestEvidenceFindingAttribution(unittest.TestCase):
    """Regression tests for a confirmed bug found during architecture
    review: `run`'s submission loop used to pass the FULL result.evidences
    list to submit_finding() for EVERY finding, so an experiment emitting
    multiple distinct findings in one run (e.g. exp02, one per detected
    table) had every finding incorrectly cross-linked to every OTHER
    finding's evidence too. Fixed by scoping submitted evidence to each
    finding via finding.evidence_ids (now populated by experiments at
    construction time) -- see cli.py's `run` command and
    docs/architecture/DOMAIN_API.md section 4/5, which already documented
    evidence as being specific to the finding it's submitted with.
    """

    def setUp(self):
        self.runner = CliRunner()

    def test_two_findings_in_one_run_get_distinct_evidence_not_cross_linked(self):
        import mtklab.experiments.exp00_dummy.exp00_dummy as exp00_mod
        from mtklab.core.experiment import ExperimentResult
        from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind

        def fake_run(self, ctx):
            ev_a = Evidence(
                experiment_id=self.experiment_id, evidence_type=EvidenceType.MANUAL_ANNOTATION,
                confidence=ConfidenceLevel.CANDIDATE, description="Evidence A",
                source_offset=0x1000, source_size=16, data={"which": "A"},
            )
            ev_b = Evidence(
                experiment_id=self.experiment_id, evidence_type=EvidenceType.MANUAL_ANNOTATION,
                confidence=ConfidenceLevel.CANDIDATE, description="Evidence B",
                source_offset=0x9000, source_size=16, data={"which": "B"},
            )
            finding_a = Finding(
                experiment_id=self.experiment_id, kind=FindingKind.REGION, offset=0x1000, size=16,
                label="Finding A", evidence_ids=[ev_a.evidence_id],
            )
            finding_b = Finding(
                experiment_id=self.experiment_id, kind=FindingKind.REGION, offset=0x9000, size=16,
                label="Finding B", evidence_ids=[ev_b.evidence_id],
            )
            return ExperimentResult(
                experiment_id=self.experiment_id, status="success", summary="two findings",
                findings=[finding_a, finding_b], evidences=[ev_a, ev_b],
            )

        original_run = exp00_mod.Exp00Dummy.run
        exp00_mod.Exp00Dummy.run = fake_run
        try:
            with self.runner.isolated_filesystem():
                self.runner.invoke(cli, ["init-project", "proj"])
                result = self.runner.invoke(cli, ["run", "--project", "proj", "exp00_dummy"])
                self.assertEqual(result.exit_code, 0, result.output)

                import sqlite3
                conn = sqlite3.connect("data/projects/proj/evidence.db")
                conn.row_factory = sqlite3.Row

                findings = conn.execute("SELECT finding_id, offset FROM findings ORDER BY offset").fetchall()
                self.assertEqual(len(findings), 2)
                finding_at_1000 = next(f for f in findings if f["offset"] == 0x1000)
                finding_at_9000 = next(f for f in findings if f["offset"] == 0x9000)

                linked_to_1000 = conn.execute(
                    "SELECT e.description FROM evidences e "
                    "JOIN finding_evidences fe ON fe.evidence_id = e.evidence_id "
                    "WHERE fe.finding_id = ?",
                    (finding_at_1000["finding_id"],),
                ).fetchall()
                linked_to_9000 = conn.execute(
                    "SELECT e.description FROM evidences e "
                    "JOIN finding_evidences fe ON fe.evidence_id = e.evidence_id "
                    "WHERE fe.finding_id = ?",
                    (finding_at_9000["finding_id"],),
                ).fetchall()
                conn.close()

                self.assertEqual([r["description"] for r in linked_to_1000], ["Evidence A"])
                self.assertEqual([r["description"] for r in linked_to_9000], ["Evidence B"])
        finally:
            exp00_mod.Exp00Dummy.run = original_run

    def test_evidence_with_no_associated_finding_is_still_persisted(self):
        """An experiment can legitimately produce evidence that doesn't
        (yet) support any specific finding -- it must still be stored
        (for provenance/future corroboration), just left unlinked."""
        import mtklab.experiments.exp00_dummy.exp00_dummy as exp00_mod
        from mtklab.core.experiment import ExperimentResult
        from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel

        def fake_run(self, ctx):
            orphan = Evidence(
                experiment_id=self.experiment_id, evidence_type=EvidenceType.MANUAL_ANNOTATION,
                confidence=ConfidenceLevel.CANDIDATE, description="Orphan evidence",
                source_offset=0x2000, source_size=16, data={"orphan": True},
            )
            return ExperimentResult(
                experiment_id=self.experiment_id, status="success", summary="orphan evidence only",
                findings=[], evidences=[orphan],
            )

        original_run = exp00_mod.Exp00Dummy.run
        exp00_mod.Exp00Dummy.run = fake_run
        try:
            with self.runner.isolated_filesystem():
                self.runner.invoke(cli, ["init-project", "proj"])
                result = self.runner.invoke(cli, ["run", "--project", "proj", "exp00_dummy"])
                self.assertEqual(result.exit_code, 0, result.output)

                import sqlite3
                conn = sqlite3.connect("data/projects/proj/evidence.db")
                rows = conn.execute("SELECT description FROM evidences").fetchall()
                conn.close()
                self.assertEqual([r[0] for r in rows], ["Orphan evidence"])
        finally:
            exp00_mod.Exp00Dummy.run = original_run


if __name__ == "__main__":
    unittest.main()
