-- Add result_json column to recall_runs for structured recall output.
ALTER TABLE recall_runs ADD COLUMN result_json TEXT;
