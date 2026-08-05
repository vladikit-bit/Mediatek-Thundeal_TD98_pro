"""Database migration management."""

import logging
import sqlite3
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages SQLite database schema migrations."""

    def __init__(self, conn: sqlite3.Connection, migrations_dir: Path):
        """
        Initialize the MigrationManager.

        Args:
            conn: An active SQLite database connection.
            migrations_dir: Path to the directory containing .sql migration files.
        """
        self.conn = conn
        self.migrations_dir = migrations_dir

    def _ensure_migrations_table(self):
        """Create the schema_migrations table if it doesn't exist."""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _get_applied_migrations(self) -> List[int]:
        """Return a list of applied migration versions."""
        self._ensure_migrations_table()
        cursor = self.conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [row[0] for row in cursor.fetchall()]

    def _get_available_migrations(self) -> List[Path]:
        """Return a sorted list of available .sql migration files."""
        if not self.migrations_dir.exists() or not self.migrations_dir.is_dir():
            return []
        files = [f for f in self.migrations_dir.iterdir() if f.is_file() and f.suffix == ".sql"]
        # Sort by filename which should be prefixed with the version (e.g., 001_initial.sql)
        files.sort(key=lambda f: f.name)
        return files

    def apply_migrations(self):
        """
        Apply all pending migrations in order.
        
        Uses explicit transactions to ensure atomicity of each migration.
        """
        applied_versions = set(self._get_applied_migrations())
        available_migrations = self._get_available_migrations()

        for migration_file in available_migrations:
            try:
                # Extract version from filename assuming format like "001_name.sql"
                version_str = migration_file.name.split("_", 1)[0]
                version = int(version_str)
            except ValueError:
                logger.warning(f"Skipping incorrectly named migration file: {migration_file.name}")
                continue

            if version in applied_versions:
                continue

            logger.info(f"Applying migration {migration_file.name} (version {version})...")
            sql_script = migration_file.read_text(encoding="utf-8")
            
            # Explicit transaction for this migration
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                self.conn.executescript(sql_script)
                self.conn.execute(
                    "INSERT INTO schema_migrations (version, filename) VALUES (?, ?)",
                    (version, migration_file.name),
                )
                self.conn.commit()
                logger.info(f"Migration {version} applied successfully.")
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Failed to apply migration {migration_file.name}. Rolled back. Error: {e}")
                raise
