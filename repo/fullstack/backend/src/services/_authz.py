"""Service-layer authorization helpers.

Two concerns live here:

- `enforce_store_access` — reject any cross-store read/write so one store
  cannot observe or mutate another store's entities. Administrators are
  the only role that bypasses (they are system-wide operators by design
  and typically have no single `store_id`).

- `require_admin` — convenience guard used by the user-management paths
  (`create_user`, `freeze_user`, `unfreeze_user`) where privilege
  escalation is the concern rather than cross-store leakage.

Both helpers raise `PermissionError` on violation so routes can translate
them into `403` responses uniformly.
"""
from typing import Optional

from ..enums.user_role import UserRole


def enforce_store_access(
    entity_store_id: Optional[int],
    actor_store_id: Optional[int],
    actor_role: str,
    *,
    entity_name: str = "entity",
) -> None:
    """Raise PermissionError unless the actor is allowed to touch this entity.

    Administrators have system-wide reach (no store context); every other
    role is pinned to its own `store_id` and cannot read or mutate rows
    outside of it.
    """
    if actor_role == UserRole.ADMINISTRATOR:
        return
    if actor_store_id is None:
        raise PermissionError(
            f"Cross-store access denied on {entity_name}: no store context"
        )
    if entity_store_id != actor_store_id:
        raise PermissionError(
            f"Cross-store access denied on {entity_name}"
        )


def require_admin(actor_role: str) -> None:
    """Raise PermissionError if the actor is not an administrator."""
    if actor_role != UserRole.ADMINISTRATOR:
        raise PermissionError("Admin privileges required")
