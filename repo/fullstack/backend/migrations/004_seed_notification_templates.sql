-- Seed the five notification templates referenced by the UI.
-- store_id IS NULL makes them system-wide defaults; stores can override
-- by inserting a row with the same template_code and their own store_id.

INSERT OR IGNORE INTO notification_templates (store_id, template_code, name, body, event_type, is_active)
VALUES
    (NULL, 'accepted',    'Ticket Accepted',         'Hi {customer_name}, your buyback ticket has been accepted. We will begin processing your items shortly.', 'ticket_accepted', 1),
    (NULL, 'rescheduled', 'Appointment Rescheduled', 'Hi {customer_name}, your appointment has been rescheduled. Please check your updated time slot.', 'ticket_rescheduled', 1),
    (NULL, 'arrived',     'Items Arrived',           'Hi {customer_name}, your items have arrived at our facility and are queued for inspection.', 'ticket_arrived', 1),
    (NULL, 'completed',   'Ticket Completed',        'Hi {customer_name}, your buyback ticket is complete. Your payout of ${payout_amount} has been processed.', 'ticket_completed', 1),
    (NULL, 'refunded',    'Refund Issued',           'Hi {customer_name}, a refund of ${refund_amount} has been issued for your ticket. Please allow 3-5 business days for processing.', 'ticket_refunded', 1);
