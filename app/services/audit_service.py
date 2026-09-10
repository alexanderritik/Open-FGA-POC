from sqlalchemy.orm import Session

from app.db.models.audit_event import AuditEvent

# No authentication exists in this PoC, so there is no verified caller
# identity to attribute business-record mutations to yet. Real actor
# tracking (once an identity source exists) and the rest of the audit
# workflow (querying/reporting) are addressed in a later step; this
# minimal helper only appends events using the schema already in place.
SYSTEM_ACTOR = "system"


def record_event(
    db: Session,
    *,
    event_type: str,
    resource_type: str,
    resource_id: str,
    action: str,
    result: str,
    actor: str = SYSTEM_ACTOR,
    event_metadata: dict | None = None,
) -> AuditEvent:
    """Adds an AuditEvent to `db` without committing — callers include this
    in the same transaction as the business-record change it documents, so
    the two either both persist or both roll back together."""
    event = AuditEvent(
        event_type=event_type,
        actor=actor,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        result=result,
        event_metadata=event_metadata,
    )
    db.add(event)
    return event
