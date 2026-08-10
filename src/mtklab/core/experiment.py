"""Experiment base classes and registry."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .evidence import Evidence, Finding


@dataclass
class ExperimentContext:
    """Sandboxed context passed to each experiment run."""

    firmware_path: Path
    ree_payload_path: Path
    config: dict[str, Any]
    evidence_db: "EvidenceDatabase"  # Forward reference
    artifacts_dir: Path
    shared_data: dict[str, Any] = field(default_factory=dict)
    progress: "ProgressReporter" = field(default_factory=lambda: ProgressReporter())
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("mtklab.experiment"))
    # Execution session identifier (MTKLAB-010). None when an experiment is
    # run outside the `mtklab run` CLI flow (e.g. directly in unit tests or
    # scripts) -- this is an explicit, documented default, not an error
    # condition; nothing in the framework requires run_id to be set.
    #
    # NOTE: MTKLAB-010's spec places this on `src/mtklab/core/context.py`,
    # but no such file exists in this codebase -- ExperimentContext has
    # always lived here in experiment.py. Added in place rather than
    # splitting the dataclass into a new file, per "prefer incremental
    # improvements over refactoring."
    run_id: str | None = None

    def get_findings(
        self, experiment_id: str | None = None, near_offset: int | None = None, radius: int = 0
    ) -> list[Finding]:
        """Query previously-persisted findings, optionally scoped to a
        specific experiment_id and/or an offset window (`near_offset` +/-
        `radius`). Implements the ctx.get_findings() capability documented
        in docs/architecture/DOMAIN_API.md section 5 ("Inter-Experiment
        Communication: Downstream experiments read persistent findings via
        ctx.get_findings() or ctx.get_evidences()") -- documented there
        since before this method actually existed.

        Intended use: an experiment checking whether an offset it's
        investigating was already reported by an earlier experiment in
        this run (or a previous run), e.g. for corroboration --
        `ctx.get_findings(near_offset=0x5950, radius=64)`. This is a
        read-only query against already-committed data; it does not
        replace or bypass EvidenceEngine.submit_finding()'s deduplication
        for findings the CALLING experiment produces itself.
        """
        offset_range = (near_offset - radius, near_offset + radius + 1) if near_offset is not None else None
        return self.evidence_db.query_findings(experiment_id=experiment_id, offset_range=offset_range)

    def get_evidences(
        self, experiment_id: str | None = None, near_offset: int | None = None, radius: int = 0
    ) -> list[Evidence]:
        """Query previously-persisted evidence, optionally scoped to a
        specific experiment_id and/or an offset window. See get_findings()
        docstring -- same DOMAIN_API.md section 5 capability, evidence
        side."""
        offset_range = (near_offset - radius, near_offset + radius + 1) if near_offset is not None else None
        return self.evidence_db.query_evidences(experiment_id=experiment_id, offset_range=offset_range)


@dataclass
class ExperimentResult:
    """Standardized output of every experiment."""

    experiment_id: str
    status: Literal["success", "partial", "failed"]
    summary: str
    findings: list[Finding] = field(default_factory=list)
    evidences: list[Evidence] = field(default_factory=list)
    hypotheses: list["Hypothesis"] = field(default_factory=list)
    artifacts: dict[str, Path] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    # Snapshot of the experiment's self.parameters at the time it ran
    # (provenance gap found during architecture review: db.py's
    # store_experiment_result() has always written
    # json.dumps(getattr(result, "parameters", {})) into the experiments
    # table's parameters_json column, but ExperimentResult never actually
    # had a `parameters` attribute -- so that column has always been
    # empty, for every run, ever. Populated by cli.py's `run` command
    # (result.parameters = dict(exp.parameters)) right after exp.run(ctx)
    # returns, uniformly for every experiment regardless of which return
    # path it took, rather than requiring every experiment to set this
    # itself on every return statement.
    #
    # KNOWN LIMITATION (flagged, not fixed here): the experiments table is
    # keyed by experiment_id and overwritten on each run (INSERT OR
    # REPLACE), so this only ever reflects the MOST RECENT run's
    # parameters, not the exact parameters active when a specific
    # already-persisted Finding/Evidence was originally created. True
    # per-observation parameter provenance would need its own column on
    # the per-invocation experiment_runs table (MTKLAB-009/010) instead,
    # which needs a schema migration and is left for a follow-up.
    parameters: dict[str, Any] = field(default_factory=dict)

    def mark_completed(self):
        self.completed_at = datetime.utcnow()
        if "duration_seconds" not in self.metadata:
            self.metadata["duration_seconds"] = (self.completed_at - self.started_at).total_seconds()


class ProgressReporter:
    """Simple progress reporting for long-running experiments."""

    def __init__(self):
        self._current = 0
        self._total = 0
        self._desc = ""

    def start(self, total: int, desc: str = ""):
        self._total = total
        self._current = 0
        self._desc = desc

    def update(self, n: int = 1):
        self._current += n

    def finish(self):
        self._current = self._total


class Experiment(abc.ABC):
    """Base class for all experiments."""

    # Required class attributes
    experiment_id: str
    display_name: str
    description: str
    version: str = "1.0.0"

    # Dependencies - other experiment IDs whose results this needs
    requires: list[str] = field(default_factory=list)

    # Optional parameters with defaults
    parameters: dict[str, Any] = field(default_factory=dict)

    @abc.abstractmethod
    def run(self, ctx: ExperimentContext) -> ExperimentResult:
        """Execute the experiment. Must be deterministic for same inputs."""
        ...

    def validate_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and merge with defaults. Override if needed."""
        return {**self.parameters, **params}

    def get_required_experiments(self) -> list[str]:
        return self.requires


class ExperimentRegistry:
    """Manages experiment discovery, dependencies, and execution order."""

    def __init__(self):
        self._experiments: dict[str, Experiment] = {}

    def register(self, exp: Experiment):
        if exp.experiment_id in self._experiments:
            raise ValueError(f"Experiment {exp.experiment_id} already registered")
        self._experiments[exp.experiment_id] = exp

    def get(self, exp_id: str) -> Experiment:
        if exp_id not in self._experiments:
            raise KeyError(f"Experiment {exp_id} not found")
        return self._experiments[exp_id]

    def all(self) -> list[Experiment]:
        return list(self._experiments.values())

    def resolve_order(self, target_ids: list[str]) -> list[str]:
        """Topological sort respecting dependencies."""
        visited = set()
        temp = set()
        order = []

        def visit(exp_id: str):
            if exp_id in temp:
                raise ValueError(f"Circular dependency detected involving {exp_id}")
            if exp_id in visited:
                return
            temp.add(exp_id)
            exp = self._experiments[exp_id]
            for dep in exp.requires:
                visit(dep)
            temp.remove(exp_id)
            visited.add(exp_id)
            order.append(exp_id)

        for tid in target_ids:
            visit(tid)
        return order

    def prepare_context(self, exp_id: str, base_ctx: ExperimentContext) -> ExperimentContext:
        """Inject shared data from completed dependency experiments."""
        exp = self._experiments[exp_id]
        shared_data = base_ctx.shared_data.copy()

        for dep_id in exp.requires:
            artifacts = base_ctx.evidence_db.get_experiment_artifacts(dep_id)
            shared_data[dep_id] = artifacts

        return ExperimentContext(
            **{k: v for k, v in base_ctx.__dict__.items() if k != "shared_data"},
            shared_data=shared_data,
        )

    @classmethod
    def from_config(cls, config_path: Path) -> "ExperimentRegistry":
        """Load experiments from YAML config."""
        import yaml

        registry = cls()
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        for exp_cfg in config.get("experiments", []):
            module_path = exp_cfg["module"]
            module_name, class_name = module_path.rsplit(".", 1)
            module = __import__(module_name, fromlist=[class_name])
            exp_class = getattr(module, class_name)
            exp = exp_class()
            exp.requires = exp_cfg.get("requires", [])
            exp.parameters = exp_cfg.get("parameters", {})
            registry.register(exp)
        return registry

    def auto_discover(self, package: str = "mtklab.experiments") -> int:
        """Automatically discover and register experiments from a package."""
        import importlib
        from pathlib import Path

        count = 0
        pkg = importlib.import_module(package)
        for pkg_path in pkg.__path__:
            base_path = Path(pkg_path)
            for py_file in base_path.glob("**/*.py"):
                if py_file.name.startswith("_"):
                    continue
                rel_path = py_file.relative_to(base_path)
                mod_parts = [package] + list(rel_path.with_suffix("").parts)
                modname = ".".join(mod_parts)
                try:
                    mod = importlib.import_module(modname)
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, Experiment)
                            and attr is not Experiment
                            and hasattr(attr, "experiment_id")
                        ):
                            if attr.experiment_id not in self._experiments:
                                exp = attr()
                                self.register(exp)
                                count += 1
                except Exception:
                    pass  # Skip modules that fail to import
        return count