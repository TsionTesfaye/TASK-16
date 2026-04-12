-- Bootstrap flag migration
-- Adds a one-shot marker that locks the /api/auth/bootstrap endpoint
-- after the first administrator has been created.

ALTER TABLE settings ADD COLUMN bootstrap_completed INTEGER NOT NULL DEFAULT 0;
