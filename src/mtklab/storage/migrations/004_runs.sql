-- Migration 004: Create runs and experiment_runs tracking tables
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    command TEXT,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    experiment_run_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    duration_seconds REAL,
    metrics_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_run_id ON experiment_runs(run_id);
