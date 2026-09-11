"""Business logic for Structures.

Structure's business data (name, created_at) lives in the application DB
(app/db/models/structure.py has no zone_id/project_id column). Its parent
— either a Project directly, or a Zone at any nesting depth — is recorded
exclusively as an OpenFGA tuple (`structure:<id>#parent@project:<id>` or
`structure:<id>#parent@zone:<id>`), written through AuthorizationService —
never as SQL.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService
from app.db.models.audit_event import AuditEvent
from app.db.models.structure import Structure
from app.schemas.structure import StructureCreate, StructureRead
from app.services import audit_service, project_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError

logger = logging.getLogger(__name__)

PROJECT_TYPE = "project"
ZONE_TYPE = "zone"
STRUCTURE_TYPE = "structure"
PARENT_RELATION = "parent"


async def _assert_parent_exists(db: Session, auth: AuthorizationService, parent_type: str, parent_id: str) -> None:
    if parent_type == PROJECT_TYPE:
        if not project_service.project_exists(db, parent_id):
            raise ResourceNotFoundError("project", parent_id)
        return

    if await auth.read_parent(ZONE_TYPE, parent_id) is None:
        raise ResourceNotFoundError("zone", parent_id)


async def create_structure(db: Session, auth: AuthorizationService, payload: StructureCreate) -> StructureRead:
    await _assert_parent_exists(db, auth, payload.parent_type, payload.parent_id)

    structure = Structure(id=payload.id, name=payload.name)
    db.add(structure)
    audit_service.record_event(
        db,
        event_type="structure.created",
        resource_type="structure",
        resource_id=payload.id,
        action="create",
        result="success",
        event_metadata={"name": payload.name, "parent_type": payload.parent_type, "parent_id": payload.parent_id},
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateResourceError("structure", "id", payload.id) from exc

    db.refresh(structure)

    try:
        await auth.write_tuple(
            user=f"{payload.parent_type}:{payload.parent_id}",
            relation=PARENT_RELATION,
            object=f"{STRUCTURE_TYPE}:{payload.id}",
        )
    except AuthorizationServiceUnavailableError:
        # The business row was committed but the authorization relationship
        # was not: compensate by removing it rather than leaving a structure
        # that exists in the DB but is unreachable in the hierarchy (nothing
        # would ever list or authorize it), then fail the request.
        logger.error(
            "OpenFGA write failed after structure %r was committed; rolling back the business row", payload.id
        )
        db.delete(structure)
        _delete_audit_and_commit(db, payload.id)
        raise

    return StructureRead(
        id=structure.id,
        name=structure.name,
        created_at=structure.created_at,
        parent_type=payload.parent_type,
        parent_id=payload.parent_id,
    )


def _delete_audit_and_commit(db: Session, structure_id: str) -> None:
    db.query(AuditEvent).filter(
        AuditEvent.resource_type == "structure",
        AuditEvent.resource_id == structure_id,
        AuditEvent.event_type == "structure.created",
    ).delete(synchronize_session=False)
    db.commit()


async def get_structure(db: Session, auth: AuthorizationService, structure_id: str) -> StructureRead:
    structure = db.get(Structure, structure_id)
    if structure is None:
        raise ResourceNotFoundError("structure", structure_id)

    parent_ref = await auth.read_parent(STRUCTURE_TYPE, structure_id)
    parent_type: str | None = None
    parent_id: str | None = None
    if parent_ref is not None:
        parent_type, _, parent_id = parent_ref.partition(":")
    else:
        logger.warning("Structure %r has a business row but no OpenFGA parent tuple", structure_id)

    return StructureRead(
        id=structure.id,
        name=structure.name,
        created_at=structure.created_at,
        parent_type=parent_type,
        parent_id=parent_id,
    )


def list_structures(db: Session) -> list[Structure]:
    return list(db.query(Structure).order_by(Structure.created_at).all())


def structure_exists(db: Session, structure_id: str) -> bool:
    return db.get(Structure, structure_id) is not None
