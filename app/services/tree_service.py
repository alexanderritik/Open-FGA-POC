"""Authorization-aware, pruned resource tree for GET /clients/{id}/tree.

The tree shape (client -> project -> zone -> ... -> structure) is derived
entirely from the application DB (client/project/structure business rows)
plus OpenFGA relationships (zone hierarchy, and every visibility decision).
No SQL-based Zone hierarchy is introduced or reproduced here.

Pruning rule: a node appears in the tree if the requesting user can view
it directly/by inheritance (`viewer` check), OR if at least one of its
descendants can be viewed — the latter is what lets an ancestor the user
has no direct access to still appear as a "pass-through" container on the
path down to something they can see (e.g. a zone-level grant three levels
deep still needs the client and project nodes rendered to have somewhere
to attach to). A leaf structure has no descendants, so it appears only
when directly visible (itself, or via inheritance from an ancestor grant).

Anti-enumeration: a client that doesn't exist and a client the user has
no visibility into anywhere in its tree produce the identical outcome
(ResourceNotFoundError -> 404 at the API layer) so neither response shape
nor status code reveals which case occurred to the caller. The audit log
still records the distinction internally (see get_client_tree).
"""

from sqlalchemy.orm import Session

from app.authorization.service import AuthorizationService
from app.db.models.client import Client
from app.db.models.project import Project
from app.db.models.structure import Structure
from app.schemas.tree import TreeNode
from app.services import audit_service
from app.services.exceptions import ResourceNotFoundError

VIEWER_RELATION = "viewer"
PARENT_RELATION = "parent"


async def _build_structure_node(db: Session, auth: AuthorizationService, structure_id: str, user: str) -> TreeNode | None:
    if not await auth.check(user, VIEWER_RELATION, f"structure:{structure_id}"):
        return None
    structure = db.get(Structure, structure_id)
    # A structure row missing here (OpenFGA has the tuple, DB doesn't have
    # the row) would be a data-consistency bug elsewhere, not something to
    # crash the tree on — render it with no name rather than fail.
    name = structure.name if structure is not None else None
    return TreeNode(type="structure", id=structure_id, name=name, children=[])


async def _build_zone_node(db: Session, auth: AuthorizationService, zone_id: str, user: str) -> TreeNode | None:
    zone_visible = await auth.check(user, VIEWER_RELATION, f"zone:{zone_id}")

    child_zone_refs = await auth.list_relationships(f"zone:{zone_id}", PARENT_RELATION, "zone")
    child_structure_refs = await auth.list_relationships(f"zone:{zone_id}", PARENT_RELATION, "structure")

    children: list[TreeNode] = []
    for ref in sorted(child_zone_refs):
        node = await _build_zone_node(db, auth, ref.split(":", 1)[1], user)
        if node is not None:
            children.append(node)
    for ref in sorted(child_structure_refs):
        node = await _build_structure_node(db, auth, ref.split(":", 1)[1], user)
        if node is not None:
            children.append(node)

    if not zone_visible and not children:
        return None
    return TreeNode(type="zone", id=zone_id, name=None, children=children)


async def _build_project_node(db: Session, auth: AuthorizationService, project: Project, user: str) -> TreeNode | None:
    project_visible = await auth.check(user, VIEWER_RELATION, f"project:{project.id}")

    zone_refs = await auth.list_relationships(f"project:{project.id}", PARENT_RELATION, "zone")
    # A Structure can be parented directly to a Project (no Zone in
    # between) as well as to a Zone — both are direct OpenFGA children of
    # the project, so both must be fetched here.
    direct_structure_refs = await auth.list_relationships(f"project:{project.id}", PARENT_RELATION, "structure")

    children: list[TreeNode] = []
    for ref in sorted(zone_refs):
        node = await _build_zone_node(db, auth, ref.split(":", 1)[1], user)
        if node is not None:
            children.append(node)
    for ref in sorted(direct_structure_refs):
        node = await _build_structure_node(db, auth, ref.split(":", 1)[1], user)
        if node is not None:
            children.append(node)

    if not project_visible and not children:
        return None
    return TreeNode(type="project", id=project.id, name=project.name, children=children)


async def _build_client_tree(db: Session, auth: AuthorizationService, client: Client, user: str) -> TreeNode | None:
    client_visible = await auth.check(user, VIEWER_RELATION, f"client:{client.id}")

    projects = db.query(Project).filter(Project.client_id == client.id).order_by(Project.created_at).all()
    children: list[TreeNode] = []
    for project in projects:
        node = await _build_project_node(db, auth, project, user)
        if node is not None:
            children.append(node)

    if not client_visible and not children:
        return None
    return TreeNode(type="client", id=client.id, name=client.name, children=children)


async def get_client_tree(db: Session, auth: AuthorizationService, client_id: str, user: str) -> TreeNode:
    client = db.get(Client, client_id)
    if client is None:
        audit_service.record_event(
            db,
            event_type="tree.access",
            actor=user,
            resource_type="client",
            resource_id=client_id,
            action="read_tree",
            result="denied",
            event_metadata={"reason": "not_found"},
        )
        db.commit()
        raise ResourceNotFoundError("client", client_id)

    tree = await _build_client_tree(db, auth, client, user)

    if tree is None:
        audit_service.record_event(
            db,
            event_type="tree.access",
            actor=user,
            resource_type="client",
            resource_id=client_id,
            action="read_tree",
            result="denied",
            event_metadata={"reason": "unauthorized"},
        )
        db.commit()
        # Same error as the "doesn't exist" branch above and the same 404
        # at the API layer: existence and authorization are indistinguishable
        # to the caller by design.
        raise ResourceNotFoundError("client", client_id)

    audit_service.record_event(
        db,
        event_type="tree.access",
        actor=user,
        resource_type="client",
        resource_id=client_id,
        action="read_tree",
        result="success",
    )
    db.commit()
    return tree
