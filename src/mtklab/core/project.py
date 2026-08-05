"""Project / Firmware Session management."""

import yaml
from pathlib import Path
from typing import Any, Dict

from mtklab.core.experiment import ExperimentContext
from mtklab.storage.artifacts import ArtifactManager
from mtklab.storage.db import EvidenceDatabase


class Project:
    """
    Root object representing a Firmware Session.
    
    Owns the lifecycle of the database, artifact manager, configuration, 
    and experiment execution contexts for a single firmware analysis project.
    """

    def __init__(self, name: str, base_dir: Path = Path("data/projects")):
        """
        Initialize a new or existing project session.
        
        Args:
            name: The unique name of the project session.
            base_dir: The root directory containing all project sessions.
        """
        self.name = name
        self.project_dir = base_dir / name
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configuration if it exists
        self.config_path = self.project_dir / "config.yaml"
        self.config: Dict[str, Any] = {}
        if self.config_path.exists():
            self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            
        # Initialize subsystem managers
        self.artifacts = ArtifactManager(self.project_dir)
        
        # Database setup
        # Migrations are expected to be in the package: src/mtklab/storage/migrations
        # We need a robust way to find this directory regardless of current working dir.
        migrations_dir = Path(__file__).parent.parent / "storage" / "migrations"
        
        db_path = self.project_dir / "evidence.db"
        self.db = EvidenceDatabase(db_path, migrations_dir)

    def close(self):
        """Clean up project resources."""
        self.db.close()

    def get_firmware_path(self) -> Path:
        """Get the main firmware path from config or defaults."""
        fw_path = self.config.get("firmware", {}).get("files", {}).get("ota")
        if fw_path:
            return Path(fw_path)
        # Default assumption if not configured
        return self.project_dir / "firmware" / "upgrade_image.pkg"

    def get_ree_payload_path(self) -> Path:
        """Get the REE payload path from config or defaults."""
        ree_path = self.config.get("firmware", {}).get("files", {}).get("ree_payload")
        if ree_path:
            return Path(ree_path)
        return self.project_dir / "firmware" / "ree_payload.bin"

    def create_experiment_context(self, experiment_id: str) -> ExperimentContext:
        """
        Create a sandboxed execution context for a specific experiment.
        
        Args:
            experiment_id: The ID of the experiment being run.
        """
        # Ensure the experiment output directory exists
        artifacts_dir = self.artifacts._get_experiment_dir(experiment_id)
        
        return ExperimentContext(
            firmware_path=self.get_firmware_path(),
            ree_payload_path=self.get_ree_payload_path(),
            config=self.config,
            evidence_db=self.db,
            artifacts_dir=artifacts_dir,
            shared_data={},  # Registry injects this during resolve_order
        )
