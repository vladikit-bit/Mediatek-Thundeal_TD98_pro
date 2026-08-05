"""Artifact storage management."""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from mtklab.utils import json


class ArtifactManager:
    """Manages file-based artifacts for a project session."""

    def __init__(self, project_dir: Path):
        """
        Initialize the ArtifactManager.

        Args:
            project_dir: The root directory for the current project session.
        """
        self.project_dir = project_dir
        self.experiments_dir = self.project_dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

    def _get_experiment_dir(self, experiment_id: str) -> Path:
        """Get the directory for a specific experiment's artifacts."""
        exp_dir = self.experiments_dir / experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        return exp_dir

    def store_json(self, experiment_id: str, filename: str, data: Any) -> Path:
        """Store structured data as a JSON artifact."""
        if not filename.endswith(".json"):
            filename += ".json"
        filepath = self._get_experiment_dir(experiment_id) / filename
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return filepath

    def read_json(self, experiment_id: str, filename: str) -> Any:
        """Read a JSON artifact."""
        filepath = self._get_experiment_dir(experiment_id) / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Artifact not found: {filepath}")
        return json.loads(filepath.read_text(encoding="utf-8"))

    def store_csv(self, experiment_id: str, filename: str, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> Path:
        """Store tabular data as a CSV artifact."""
        if not filename.endswith(".csv"):
            filename += ".csv"
        filepath = self._get_experiment_dir(experiment_id) / filename
        
        if not rows and not fieldnames:
            # Empty file
            filepath.touch()
            return filepath

        if not fieldnames:
            fieldnames = list(rows[0].keys())

        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
        return filepath

    def store_binary(self, experiment_id: str, filename: str, data: bytes) -> Path:
        """Store raw binary data."""
        filepath = self._get_experiment_dir(experiment_id) / filename
        filepath.write_bytes(data)
        return filepath

    def get_artifact_path(self, experiment_id: str, filename: str) -> Path:
        """Get the absolute path for an artifact without reading it."""
        return self._get_experiment_dir(experiment_id) / filename
