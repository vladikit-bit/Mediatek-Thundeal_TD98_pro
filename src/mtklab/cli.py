"""MT5889 RE Laboratory - Command Line Interface."""

from __future__ import annotations

import logging
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import click
    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False
    import argparse

    class GroupStub:
        def __init__(self, fn, click_stub):
            self.fn = fn
            self.click_stub = click_stub

        def command(self, name=None):
            def decorator(cmd_fn):
                cname = name or cmd_fn.__name__.replace("_", "-")
                self.click_stub._commands[cname] = cmd_fn
                if not hasattr(cmd_fn, "_opts"):
                    cmd_fn._opts = []
                return cmd_fn
            return decorator

        def __call__(self, argv=None):
            parser = argparse.ArgumentParser(description=self.fn.__doc__ or "MT5889 RE Laboratory")
            parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
            subparsers = parser.add_subparsers(dest="subcommand")
            for cname, cfn in self.click_stub._commands.items():
                sp = subparsers.add_parser(cname, help=cfn.__doc__)
                for oargs, okwargs in getattr(cfn, "_opts", []):
                    flags = [a for a in oargs if a.startswith("-")]
                    dests = [a for a in oargs if not a.startswith("-")]
                    if flags:
                        kw = {}
                        if dests:
                            kw["dest"] = dests[0]
                        if okwargs.get("is_flag"):
                            kw["action"] = "store_true"
                        if okwargs.get("help"):
                            kw["help"] = okwargs["help"]
                        if okwargs.get("required"):
                            kw["required"] = okwargs["required"]
                        sp.add_argument(*flags, **kw)
                    else:
                        name = oargs[0].lstrip("-")
                        kw = {}
                        click_nargs = okwargs.get("nargs")
                        if click_nargs is not None:
                            # Click uses nargs=-1 on @click.argument(...) to mean
                            # "0 or more" (variadic positional). argparse has no
                            # such convention: passing -1 straight through makes
                            # argparse's _get_nargs_pattern() build '(-*%s-*)' %
                            # '-*'.join('A' * nargs) with 'A' * -1 == '', i.e. a
                            # pattern that matches ZERO tokens no matter what.
                            # Any experiment IDs actually supplied on the command
                            # line then never get consumed by this positional and
                            # surface as "unrecognized arguments" instead.
                            # Translate to argparse's own "zero or more" marker.
                            kw["nargs"] = "*" if click_nargs == -1 else click_nargs
                        sp.add_argument(name, **kw)
            parsed = parser.parse_args(argv)
            if parsed.verbose:
                logging.getLogger().setLevel(logging.DEBUG)
            if parsed.subcommand in self.click_stub._commands:
                fn = self.click_stub._commands[parsed.subcommand]
                kw = {k: v for k, v in vars(parsed).items() if k not in ("subcommand", "verbose")}
                if "experiment_ids" in kw and isinstance(kw["experiment_ids"], list):
                    kw["experiment_ids"] = tuple(kw["experiment_ids"])
                fn(**kw)
            else:
                parser.print_help()

    class ClickStub:
        def __init__(self):
            self._commands = {}

        def group(self, *args, **kwargs):
            def decorator(f):
                return GroupStub(f, self)
            return decorator

        def option(self, *args, **kwargs):
            def decorator(f):
                if not hasattr(f, "_opts"):
                    f._opts = []
                f._opts.append((args, kwargs))
                return f
            return decorator

        def argument(self, *args, **kwargs):
            def decorator(f):
                if not hasattr(f, "_opts"):
                    f._opts = []
                f._opts.append((args, kwargs))
                return f
            return decorator

        def Path(self, *args, **kwargs):
            return str

    click = ClickStub()

try:
    import yaml
except ImportError:
    yaml = None

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    import re

    class Console:
        def print(self, *args, **kwargs):
            msg = " ".join(str(a) for a in args)
            clean_msg = re.sub(r"\[/?\w+.*?\]", "", msg)
            print(clean_msg)

    class Table:
        def __init__(self, title=""):
            self.title = title
            self.columns = []
            self.rows = []

        def add_column(self, name, **kwargs):
            self.columns.append(name)

        def add_row(self, *vals):
            self.rows.append(vals)

        def __str__(self):
            out = [f"=== {self.title} ==="] if self.title else []
            out.append(" | ".join(self.columns))
            out.append("-" * 40)
            for r in self.rows:
                out.append(" | ".join(str(v) for v in r))
            return "\n".join(out)

    class Panel:
        @classmethod
        def fit(cls, text, title="", **kwargs):
            clean = re.sub(r"\[/?\w+.*?\]", "", text)
            if title:
                return f"=== {title} ===\n{clean}"
            return clean

from mtklab.core.experiment import ExperimentRegistry, ExperimentContext
from mtklab.core.evidence import EvidenceEngine
from mtklab.core.project import Project
from mtklab.storage.db import EvidenceDatabase

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mtklab.cli")


def get_project(name: str) -> Project:
    """Load a project by name."""
    return Project(name, Path("data/projects"))


def get_registry(project: Project) -> ExperimentRegistry:
    """Build the experiment registry from config."""
    registry = ExperimentRegistry()
    # Auto-discover experiments from the package
    count = registry.auto_discover("mtklab.experiments")
    logger.info(f"Discovered {count} experiments")
    
    # Apply config overrides
    config_path = Path("config/experiments.yaml")
    if config_path.exists() and yaml is not None:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for exp_cfg in config.get("experiments", []):
            exp_id = exp_cfg["id"]
            if exp_id in registry._experiments:
                exp = registry._experiments[exp_id]
                exp.requires = exp_cfg.get("requires", exp.requires)
                exp.parameters = {**exp.parameters, **exp_cfg.get("parameters", {})}
    
    return registry


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(verbose: bool):
    """MT5889 Reverse Engineering Laboratory for Thundeal TD98 Pro."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.argument("name")
@click.option("--firmware", "-f", type=click.Path(exists=True), help="Path to OTA firmware file")
@click.option("--ree-payload", "-r", type=click.Path(exists=True), help="Path to REE payload (optional)")
@click.option("--force", is_flag=True, help="Overwrite existing project")
def init_project(name: str, firmware: Optional[str], ree_payload: Optional[str], force: bool):
    """Initialize a new firmware analysis project."""
    project_dir = Path("data/projects") / name
    
    if project_dir.exists():
        if force:
            console.print(f"[yellow]Project '{name}' exists, overwriting...[/yellow]")
            shutil.rmtree(project_dir)
        else:
            console.print(f"[red]Project '{name}' already exists. Use --force to overwrite.[/red]")
            sys.exit(1)
    
    # Create project structure
    project_dir.mkdir(parents=True)
    (project_dir / "firmware").mkdir(parents=True)
    
    # Copy/symlink firmware files
    firmware_dst = project_dir / "firmware" / "upgrade_image.pkg"
    if firmware:
        shutil.copy2(firmware, firmware_dst)
        console.print(f"Copied firmware: {firmware} → {firmware_dst}")
    else:
        console.print("[yellow]No firmware provided. Place upgrade_image.pkg in data/projects/{name}/firmware/[/yellow]")
    
    ree_dst = project_dir / "firmware" / "ree_payload.bin"
    if ree_payload:
        shutil.copy2(ree_payload, ree_dst)
        console.print(f"Copied REE payload: {ree_payload} → {ree_dst}")
    else:
        console.print("[yellow]No REE payload provided. Place ree_payload.bin in data/projects/{name}/firmware/[/yellow]")
    
    # Create config.yaml
    config = {
        "firmware": {
            "name": "Thundeal TD98 Pro",
            "soc": "MT5889",
            "os": "Android TV 10",
            "files": {
                "ota": str(firmware_dst.relative_to(project_dir)) if firmware_dst.exists() else "firmware/upgrade_image.pkg",
                "ree_payload": str(ree_dst.relative_to(project_dir)) if ree_dst.exists() else "firmware/ree_payload.bin",
            }
        }
    }
    config_path = project_dir / "config.yaml"
    if yaml is not None:
        config_path.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")
    else:
        import json
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    
    console.print(Panel.fit(
        f"[green]Project '{name}' initialized successfully![/green]\n\n"
        f"Directory: {project_dir}\n"
        f"Config: {config_path}\n\n"
        f"Next steps:\n"
        f"  mtklab run --project {name} --all\n"
        f"  mtklab list-experiments --project {name}",
        title="Project Created",
        border_style="green"
    ))


@cli.command()
@click.option("--project", "-p", required=True, help="Project name")
@click.argument("experiment_ids", nargs=-1)
@click.option("--all", "run_all", is_flag=True, help="Run all discovered experiments")
@click.option("--dry-run", is_flag=True, help="Show execution order without running")
def run(project: str, experiment_ids: tuple, run_all: bool, dry_run: bool):
    """Run experiments in dependency order."""
    proj = get_project(project)
    registry = get_registry(proj)
    
    # Determine target experiments
    if run_all:
        targets = list(registry._experiments.keys())
    elif experiment_ids:
        targets = list(experiment_ids)
    else:
        console.print("[red]No experiments specified. Use --all or provide experiment IDs.[/red]")
        sys.exit(1)
    
    # Validate targets exist
    for tid in targets:
        if tid not in registry._experiments:
            console.print(f"[red]Experiment '{tid}' not found.[/red]")
            sys.exit(1)
    
    # Resolve execution order
    try:
        order = registry.resolve_order(targets)
    except ValueError as e:
        console.print(f"[red]Dependency error: {e}[/red]")
        sys.exit(1)
    
    console.print(Panel.fit(
        f"[bold]Execution Order ({len(order)} experiments)[/bold]\n" +
        "\n".join(f"  {i+1}. {eid}" for i, eid in enumerate(order)),
        title=f"Project: {project}",
        border_style="blue"
    ))
    
    if dry_run:
        console.print("[yellow]Dry run - not executing.[/yellow]")
        return

    # --- MTKLAB-010: create the parent run record before executing anything.
    # Foreign key from experiment_runs.run_id requires this row to exist
    # first (PRAGMA foreign_keys=ON, see EvidenceDatabase.__init__).
    run_id = str(uuid.uuid4())
    proj.db.create_run(
        run_id,
        project_id=project,
        command=" ".join(sys.argv),
        config={"experiment_ids": list(experiment_ids), "run_all": run_all, "dry_run": dry_run},
    )

    # Execute experiments
    engine = EvidenceEngine(proj.db)
    
    for i, exp_id in enumerate(order):
        exp = registry._experiments[exp_id]
        console.print(f"\n[cyan][{i+1}/{len(order)}] Running {exp_id}...[/cyan]")

        start_time = time.time()
        try:
            # Prepare context with dependencies
            ctx = registry.prepare_context(exp_id, proj.create_experiment_context(exp_id))
            ctx.run_id = run_id

            # Run experiment
            result = exp.run(ctx)
            result.mark_completed()
            duration = time.time() - start_time
            
            # Store experiment result first so foreign keys reference a valid experiment row
            proj.db.store_experiment_result(result)

            # Submit findings through Evidence Engine
            if result.findings or result.evidences or result.hypotheses:
                for finding in result.findings:
                    finding.experiment_id = exp_id
                    # Scope submitted evidence to THIS finding via
                    # finding.evidence_ids (populated by the experiment at
                    # construction time), not the full result.evidences
                    # pool. Passing the whole pool to every finding would
                    # incorrectly link each finding to every OTHER
                    # finding's evidence too whenever an experiment emits
                    # more than one finding per run (e.g. exp02, one per
                    # detected table) -- confirmed during development by
                    # reproducing it directly against the DB. Evidence
                    # objects the experiment produced but didn't associate
                    # with any finding (finding.evidence_ids empty on all
                    # findings) are still persisted below via
                    # store_evidence, just not linked to a finding.
                    relevant_evidence = [
                        e for e in result.evidences if e.evidence_id in finding.evidence_ids
                    ]
                    engine.submit_finding(finding, relevant_evidence)
                # Evidence not associated with any finding (if any) is
                # still persisted for provenance/dedup, just unlinked.
                linked_ids = {eid for f in result.findings for eid in f.evidence_ids}
                for ev in result.evidences:
                    if ev.evidence_id not in linked_ids:
                        proj.db.store_evidence(ev)
                for hyp in result.hypotheses:
                    hyp.hypothesis_id = hyp.hypothesis_id  # ensure set
                    proj.db.store_hypothesis(hyp)
            
            # Store artifacts
            for artifact_type, path in result.artifacts.items():
                proj.db.store_artifact_reference(exp_id, artifact_type, path, f"Artifact from {exp_id}")
            
            console.print(f"  [green]✓ {exp_id}[/green] - {result.status}: {result.summary}")

            # MTKLAB-010: record this experiment's outcome in experiment_runs.
            # result.status is "success"/"partial"/"failed"; recorded
            # uppercased (SUCCESS/PARTIAL/FAILED) -- PARTIAL is an
            # application-level extension beyond the SUCCESS/FAILED/
            # CANCELLED/RUNNING examples in MTKLAB-009 sec. 8, which
            # explicitly leaves status unconstrained at the DB level.
            #
            # Note: a "failed" ExperimentResult here did NOT raise --
            # experiments commonly return status="failed" with a populated
            # `errors` list (e.g. exp01/exp02's "REE payload not found")
            # rather than raising an uncaught exception. That is a distinct
            # path from the `except Exception` branch below, so
            # error_message must be captured here too or it silently stays
            # NULL for the most common real-world failure shape.
            proj.db.record_experiment_run(
                run_id, exp_id,
                status=result.status.upper(),
                duration_seconds=duration,
                error_message="; ".join(result.errors) if result.errors else None,
                metrics={"findings": len(result.findings), "evidences": len(result.evidences)},
            )

        except KeyboardInterrupt:
            # MTKLAB-010 edge case: Ctrl+C during an experiment records
            # CANCELLED for the in-flight experiment (not yet-unstarted
            # ones -- the run stops here) and exits cleanly rather than
            # dumping a raw traceback.
            duration = time.time() - start_time
            console.print(f"\n  [yellow]⚠ {exp_id}[/yellow] - cancelled by user")
            proj.db.record_experiment_run(
                run_id, exp_id, status="CANCELLED", duration_seconds=duration,
                error_message="Cancelled by user (SIGINT)",
            )
            console.print("[yellow]Run cancelled.[/yellow]")
            sys.exit(130)  # conventional exit code for SIGINT

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Experiment {exp_id} failed")
            console.print(f"  [red]✗ {exp_id}[/red] - failed: {e}")
            # Store failed result
            from mtklab.core.experiment import ExperimentResult
            failed_result = ExperimentResult(
                experiment_id=exp_id,
                status="failed",
                summary=str(e),
                errors=[str(e)],
            )
            failed_result.mark_completed()
            proj.db.store_experiment_result(failed_result)

            # MTKLAB-010: record the failure in experiment_runs, capturing
            # the exception message as error_message.
            proj.db.record_experiment_run(
                run_id, exp_id, status="FAILED", duration_seconds=duration,
                error_message=str(e),
            )
    
    console.print("\n[bold green]All experiments completed.[/bold green]")


@cli.command()
@click.option("--project", "-p", required=True, help="Project name")
def list_experiments(project: str):
    """List all discovered experiments with their dependencies."""
    proj = get_project(project)
    registry = get_registry(proj)
    
    table = Table(title=f"Experiments in Project '{project}'")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Version", style="dim")
    table.add_column("Requires", style="yellow")
    table.add_column("Description", style="dim")
    
    for exp in registry.all():
        table.add_row(
            exp.experiment_id,
            exp.display_name,
            exp.version,
            ", ".join(exp.requires) if exp.requires else "—",
            exp.description[:60] + "..." if len(exp.description) > 60 else exp.description
        )
    
    console.print(table)


@cli.command()
@click.option("--project", "-p", required=True, help="Project name")
@click.argument("experiment_id")
def inspect(project: str, experiment_id: str):
    """Show detailed JSON for an experiment result, or a finding's version
    history when the argument matches a logical_id or finding_id instead."""
    proj = get_project(project)
    
    # Get experiment result from DB
    cursor = proj.db._conn.execute(
        "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
    )
    row = cursor.fetchone()

    if not row:
        # MTKLAB-011: not an experiment_id -- try it as a finding lookup
        # instead (logical_id first, then legacy finding_id UUID), before
        # falling back to the original "not found" error. Tried in this
        # order, not merged into one command signature change, to keep
        # `mtklab inspect <experiment_id>` behaving exactly as before for
        # anyone already relying on it -- the MTKLAB-011 spec text assumes
        # `inspect` already looked up findings, which is not the case in
        # this codebase; see accompanying report for details.
        finding = proj.db.get_latest_finding_by_logical_id(experiment_id)
        if finding is None:
            finding = proj.db.get_finding(experiment_id)
        if finding is not None:
            _inspect_finding(proj, finding)
            return
        console.print(
            f"[red]No experiment, logical_id, or finding_id matching "
            f"'{experiment_id}' found in project '{project}'.[/red]"
        )
        sys.exit(1)
    
    from mtklab.utils import json as json_utils
    result = {
        "experiment_id": row["experiment_id"],
        "display_name": row["display_name"],
        "version": row["version"],
        "status": row["status"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "summary": row["summary"],
        "parameters": json_utils.loads(row["parameters_json"]),
        "metadata": json_utils.loads(row["metadata_json"]),
        "errors": json_utils.loads(row["errors_json"]),
    }
    
    # Get findings
    cursor = proj.db._conn.execute(
        "SELECT finding_id FROM findings WHERE experiment_id = ?", (experiment_id,)
    )
    findings = []
    for frow in cursor.fetchall():
        finding = proj.db.get_finding(frow["finding_id"])
        if finding:
            findings.append(finding.to_dict())
    
    result["findings"] = findings
    
    console.print(json_utils.dumps(result, indent=2), soft_wrap=True)


def _inspect_finding(proj: Project, finding) -> None:
    """MTKLAB-011: render a finding's full version timeline plus its
    content-addressed evidence (via the finding_evidences junction table,
    MTKLAB-008), for `mtklab inspect <logical_id_or_finding_id>`."""
    from mtklab.utils import json as json_utils

    evidences = proj.db.get_evidences_for_finding(finding.finding_id)

    result = {
        "finding_id": finding.finding_id,
        "logical_id": finding.logical_id,
        "experiment_id": finding.experiment_id,
        "kind": finding.kind.value if hasattr(finding.kind, "value") else str(finding.kind),
        "offset": finding.offset,
        "size": finding.size,
        "confidence": finding.confidence.name,
        "label": finding.label,
        "description": finding.description,
        "version_count": len(finding.versions),
        "versions": finding.versions,
        "evidence": [
            {
                "evidence_id": e.evidence_id,
                "evidence_type": str(e.evidence_type),
                "confidence": e.confidence.name,
                "description": e.description,
                "data": e.data,
            }
            for e in evidences
        ],
    }
    console.print(json_utils.dumps(result, indent=2), soft_wrap=True)


@cli.command()
@click.option("--project", "-p", required=True, help="Project name")
@click.option("--output", "-o", type=click.Path(), help="Output HTML path")
def report(project: str, output: Optional[str]):
    """Generate HTML dashboard report."""
    raise NotImplementedError("HTML report generation will be implemented in Phase 4")


@cli.command()
@click.option("--project", "-p", required=True, help="Project name")
def status(project: str):
    """Show project status summary."""
    proj = get_project(project)
    
    # Experiment counts
    cursor = proj.db._conn.execute("SELECT status, COUNT(*) as cnt FROM experiments GROUP BY status")
    exp_stats = {row["status"]: row["cnt"] for row in cursor.fetchall()}
    
    # Finding counts
    cursor = proj.db._conn.execute("SELECT confidence, COUNT(*) as cnt FROM findings GROUP BY confidence")
    find_stats = {row["confidence"]: row["cnt"] for row in cursor.fetchall()}
    
    # Hypothesis counts
    cursor = proj.db._conn.execute("SELECT status, COUNT(*) as cnt FROM hypotheses GROUP BY status")
    hyp_stats = {row["status"]: row["cnt"] for row in cursor.fetchall()}

    # MTKLAB-011: run count and unique logical_id count. Both are simple
    # COUNT queries -- naturally 0 on an empty/fresh project database
    # rather than raising (edge case sec. 8: "zero runs or zero findings").
    run_count = proj.db.count_runs()
    cursor = proj.db._conn.execute(
        "SELECT COUNT(DISTINCT logical_id) as cnt FROM findings WHERE logical_id IS NOT NULL"
    )
    logical_finding_count = cursor.fetchone()["cnt"]

    # Confidence breakdown across the three lifecycle levels (RFC.md 4.1),
    # explicitly zero-filled so the summary is stable even before any
    # findings of a given confidence exist.
    confidence_breakdown = "\n".join(
        f"  {level}: {find_stats.get(level, 0)}"
        for level in ("CANDIDATE", "PROBABLE", "VERIFIED")
    )

    console.print(Panel.fit(
        f"[bold]Project:[/bold] {project}\n"
        f"[bold]Directory:[/bold] {proj.project_dir}\n"
        f"[bold]Firmware:[/bold] {proj.get_firmware_path()}\n"
        f"[bold]REE Payload:[/bold] {proj.get_ree_payload_path()}\n\n"
        f"[bold]Runs:[/bold] {run_count} total\n\n"
        f"[bold]Experiments:[/bold] {sum(exp_stats.values())} total\n"
        + "\n".join(f"  {k}: {v}" for k, v in exp_stats.items()) + "\n\n"
        f"[bold]Findings:[/bold] {sum(find_stats.values())} total "
        f"({logical_finding_count} unique logical_id)\n"
        f"{confidence_breakdown}\n\n"
        f"[bold]Hypotheses:[/bold] {sum(hyp_stats.values())} total\n"
        + "\n".join(f"  {k}: {v}" for k, v in hyp_stats.items()),
        title="Project Status",
        border_style="green"
    ))


if __name__ == "__main__":
    cli()