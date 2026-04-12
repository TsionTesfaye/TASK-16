-- Price override request table.
--
-- Manual price overrides bypass the deterministic pricing engine, so
-- they require dual control: a different user must re-enter their
-- password before the override is applied to the ticket. The execution
-- transition (`approved` → `executed`) is one-time only.

CREATE TABLE IF NOT EXISTS price_override_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    requested_by_user_id INTEGER NOT NULL,
    approver_user_id INTEGER,
    original_payout REAL NOT NULL,
    proposed_payout REAL NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'executed', 'expired'
    )),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    approved_at TEXT,
    rejected_at TEXT,
    executed_at TEXT,
    FOREIGN KEY (ticket_id) REFERENCES buyback_tickets(id),
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
    FOREIGN KEY (approver_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_price_override_status
    ON price_override_requests(status);
CREATE INDEX IF NOT EXISTS idx_price_override_ticket
    ON price_override_requests(ticket_id);
