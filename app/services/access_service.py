"""Business logic behind /authorization/{check,grant}.

Named distinctly from app.authorization.service (the low-level OpenFGA SDK
wrapper) to keep the two apart: this module orchestrates resource-existence
validation plus audit logging around that lower-level client.
"""

from sqlalchemy.orm import Session

from app.authorization.service import AuthorizationService
from app.schemas.authorization import Permission, ResourceType
from app.services import audit_service, client_service, project_service, structure_service
from app.services.exceptions import ResourceNotFoundError

ZONE_TYPE = "zone"


async def _resource_exists(db: Session, auth: AuthorizationService, resource_type: ResourceType, resource_id: str) -> bool:
    if resource_type == "client":
        return client_service.client_exists(db, resource_id)
    if resource_type == "project":
        return project_service.project_exists(db, resource_id)
    if resource_type == "zone":
        return await auth.read_parent(ZONE_TYPE, resource_id) is not None
    if resource_type == "structure":
        return structure_service.structure_exists(db, resource_id)
    raise ValueError(f"unsupported resource_type {resource_type!r}")  # unreachable: Pydantic Literal enforces this


async def check_access(
    auth: AuthorizationService, user: str, resource_type: ResourceType, resource_id: str, permission: Permission
) -> bool:
    """Delegates entirely to OpenFGA. Raises AuthorizationServiceUnavailableError
    (fail closed) rather than returning True/False on engine failure — see
    AuthorizationService.check."""
    return await auth.check(user=user, relation=permission, object=f"{resource_type}:{resource_id}")


async def grant_access(
    db: Session,
    auth: AuthorizationService,
    user: str,
    resource_type: ResourceType,
    resource_id: str,
    permission: Permission,
) -> bool:
    """Returns True if a new grant was written, False if it already existed
    (idempotent no-op)."""
    if not await _resource_exists(db, auth, resource_type, resource_id):
        raise ResourceNotFoundError(resource_type, resource_id)

    object_ref = f"{resource_type}:{resource_id}"
    if await auth.tuple_exists(user, permission, object_ref):
        return False

    await auth.write_tuple(user=user, relation=permission, object=object_ref)
    audit_service.record_event(
        db,
        event_type="authorization.grant.created",
        resource_type=resource_type,
        resource_id=resource_id,
        action="grant",
        result="success",
        actor=user,
        event_metadata={"permission": permission},
    )
    db.commit()
    return True


async def revoke_access(
    db: Session,
    auth: AuthorizationService,
    user: str,
    resource_type: ResourceType,
    resource_id: str,
    permission: Permission,
) -> bool:
    """Returns True if a grant was removed, False if none existed
    (idempotent no-op — DELETE is safe to retry)."""
    object_ref = f"{resource_type}:{resource_id}"
    if not await auth.tuple_exists(user, permission, object_ref):
        return False

    await auth.delete_tuple(user=user, relation=permission, object=object_ref)
    audit_service.record_event(
        db,
        event_type="authorization.grant.deleted",
        resource_type=resource_type,
        resource_id=resource_id,
        action="revoke",
        result="success",
        actor=user,
        event_metadata={"permission": permission},
    )
    db.commit()
    return True
