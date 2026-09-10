"""Business logic for Zones.

Zone is deliberately NOT a SQLAlchemy model and has no table: its identity,
its parent (project or another zone), and its children exist only as
OpenFGA tuples (`zone:<id>#parent@<project:id|zone:id>`). Every function
here reads/writes that hierarchy exclusively through AuthorizationService
(app/authorization/service.py) — never SQL — so OpenFGA remains the single
source of truth for the hierarchy shape.

The only SQL touched in this module is a read-only existence check against
the `projects` table (app/services/project_service.py), needed to validate
a zone's parent when that parent is a project.
"""

import logging

from sqlalchemy.orm import Session

from app.authorization.service import AuthorizationService
from app.schemas.zone import ZoneChildren, ZoneCreate, ZoneRead
from app.services import audit_service, project_service
from app.services.exceptions import CircularReferenceError, DuplicateResourceError, ResourceNotFoundError

logger = logging.getLogger(__name__)

ZONE_TYPE = "zone"
PROJECT_TYPE = "project"
STRUCTURE_TYPE = "structure"
PARENT_RELATION = "parent"

# Guards against an unbounded walk if the stored tuple data were ever
# inconsistent (e.g. hand-edited); a real tree is never anywhere near this
# deep, so hitting it always indicates a bug, not a legitimate hierarchy.
MAX_ANCESTOR_DEPTH = 1000


def _ref(object_type: str, object_id: str) -> str:
    return f"{object_type}:{object_id}"


def _parse_ref(ref: str) -> tuple[str, str]:
    object_type, _, object_id = ref.partition(":")
    return object_type, object_id


async def _assert_parent_exists(db: Session, auth: AuthorizationService, parent_type: str, parent_id: str) -> None:
    if parent_type == PROJECT_TYPE:
        if not project_service.project_exists(db, parent_id):
            raise ResourceNotFoundError("project", parent_id)
        return

    if await auth.read_parent(ZONE_TYPE, parent_id) is None:
        raise ResourceNotFoundError("zone", parent_id)


async def _assert_no_cycle(auth: AuthorizationService, new_zone_id: str, parent_type: str, parent_id: str) -> None:
    """Ensures creating `zone:<new_zone_id>` with the given parent cannot
    make it its own ancestor.

    Because a parent must already exist before it can be referenced (see
    `_assert_parent_exists`) and a zone's parent is set exactly once at
    creation (never re-parented by this API), `new_zone_id` can never
    actually appear among its own proposed ancestors in practice — that
    would require an id to be its own ancestor before it was ever created.
    The self-reference check below is the one directly reachable case; the
    ancestor walk beyond it is defense-in-depth against future code paths
    (e.g. a re-parent/move operation) that might relax that invariant.
    """
    if parent_type == ZONE_TYPE and parent_id == new_zone_id:
        raise CircularReferenceError("zone", new_zone_id)

    if parent_type != ZONE_TYPE:
        return

    current_type, current_id = ZONE_TYPE, parent_id
    for _ in range(MAX_ANCESTOR_DEPTH):
        parent_ref = await auth.read_parent(current_type, current_id)
        if parent_ref is None:
            return
        current_type, current_id = _parse_ref(parent_ref)
        if current_type == ZONE_TYPE and current_id == new_zone_id:
            raise CircularReferenceError("zone", new_zone_id)
        if current_type == PROJECT_TYPE:
            return
    raise CircularReferenceError("zone", new_zone_id)


async def create_zone(db: Session, auth: AuthorizationService, payload: ZoneCreate) -> tuple[ZoneRead, bool]:
    """Returns (zone, created) — created=False means the identical
    id+parent combination already existed and this call was a no-op
    (idempotent retry) rather than a fresh write."""
    requested_parent_ref = _ref(payload.parent_type, payload.parent_id)

    existing_parent_ref = await auth.read_parent(ZONE_TYPE, payload.id)
    if existing_parent_ref is not None:
        if existing_parent_ref == requested_parent_ref:
            return ZoneRead(id=payload.id, parent_type=payload.parent_type, parent_id=payload.parent_id), False
        raise DuplicateResourceError("zone", "id", payload.id)

    # Self/circular reference is checked before existence: it's a
    # structurally invalid request regardless of whether the parent exists,
    # and "you can't be your own parent" is a clearer error than "parent
    # not found" for e.g. a brand-new zone naming itself as its own parent.
    await _assert_no_cycle(auth, payload.id, payload.parent_type, payload.parent_id)
    await _assert_parent_exists(db, auth, payload.parent_type, payload.parent_id)

    await auth.write_tuple(user=requested_parent_ref, relation=PARENT_RELATION, object=_ref(ZONE_TYPE, payload.id))

    audit_service.record_event(
        db,
        event_type="zone.relationship.created",
        resource_type="zone",
        resource_id=payload.id,
        action="create",
        result="success",
        event_metadata={"parent_type": payload.parent_type, "parent_id": payload.parent_id},
    )
    db.commit()

    return ZoneRead(id=payload.id, parent_type=payload.parent_type, parent_id=payload.parent_id), True


async def get_zone(auth: AuthorizationService, zone_id: str) -> ZoneRead:
    parent_ref = await auth.read_parent(ZONE_TYPE, zone_id)
    if parent_ref is None:
        raise ResourceNotFoundError("zone", zone_id)
    parent_type, parent_id = _parse_ref(parent_ref)
    return ZoneRead(id=zone_id, parent_type=parent_type, parent_id=parent_id)


async def list_zones_under_project(db: Session, auth: AuthorizationService, project_id: str) -> list[ZoneRead]:
    if not project_service.project_exists(db, project_id):
        raise ResourceNotFoundError("project", project_id)

    zone_refs = await auth.list_relationships(_ref(PROJECT_TYPE, project_id), PARENT_RELATION, ZONE_TYPE)
    return [
        ZoneRead(id=_parse_ref(ref)[1], parent_type="project", parent_id=project_id) for ref in sorted(zone_refs)
    ]


async def get_zone_children(auth: AuthorizationService, zone_id: str) -> ZoneChildren:
    if await auth.read_parent(ZONE_TYPE, zone_id) is None:
        raise ResourceNotFoundError("zone", zone_id)

    zone_ref = _ref(ZONE_TYPE, zone_id)
    child_zone_refs = await auth.list_relationships(zone_ref, PARENT_RELATION, ZONE_TYPE)
    child_structure_refs = await auth.list_relationships(zone_ref, PARENT_RELATION, STRUCTURE_TYPE)

    return ZoneChildren(
        zone_id=zone_id,
        child_zones=sorted(_parse_ref(ref)[1] for ref in child_zone_refs),
        child_structures=sorted(_parse_ref(ref)[1] for ref in child_structure_refs),
    )
