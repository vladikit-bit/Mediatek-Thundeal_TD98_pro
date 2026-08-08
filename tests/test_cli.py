"""Integration tests for the CLI (MTKLAB-010 run tracking, MTKLAB-011
status/inspect enhancements), using Click's real CliRunner against an
isolated filesystem so nothing touches the actual data/projects directory."""

import json
import sqlite3
import unittest

from click.testing import CliRunner

from mtklab.cli import cli


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


if __name__ == "__main__":
    unittest.main()
