"""Data masking — shows only the minimum necessary information.

Sensitive fields are masked by default in API responses and exports.
Only explicit, audited reveal paths should show unmasked values.
"""
from typing import Optional


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """Mask a phone number, showing only the last 4 digits.

    '555-123-4567' -> '•••••••4567'
    """
    if phone is None or phone == "":
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) < 4:
        return "****"
    return "•" * (len(digits) - 4) + digits[-4:]


def mask_address(address: Optional[str]) -> Optional[str]:
    """Return a redacted placeholder for addresses."""
    if address is None or address == "":
        return None
    return "[REDACTED ADDRESS]"


def mask_last4(value: Optional[str]) -> Optional[str]:
    """Mask a generic short field showing only its last 4 characters.

    Used for displaying pre-stored last-4 phone fields with leading bullets.
    """
    if value is None or value == "":
        return None
    s = str(value)
    if len(s) >= 4:
        return "••••" + s[-4:]
    return "••••"


def mask_email(email: Optional[str]) -> Optional[str]:
    """Mask an email address: j***@example.com"""
    if email is None or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if not local:
        return "***@" + domain
    return local[0] + "***@" + domain
