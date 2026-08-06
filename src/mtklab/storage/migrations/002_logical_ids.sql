-- Migration 002: Add logical_id column to findings table
ALTER TABLE findings ADD COLUMN logical_id TEXT;
CREATE INDEX IF NOT EXISTS idx_findings_logical_id ON findings(logical_id);
