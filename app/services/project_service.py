"""Business logic for Projects.

Project's business data (client_id, name, created_at) lives in the
application DB. Its authorization parent is recorded exclusively as an
OpenFGA tuple (`project:<id>#parent@client:<client_id>`), written through
AuthorizationService — mirroring app/services/structure_service.py.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService
from app.db.models.audit_event import AuditEvent
from app.db.models.client import Client
from app.db.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead
from app.services import audit_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError

logger = logging.getLogger(__name__)

CLIENT_TYPE = "client"
PROJECT_TYPE = "project"
PARENT_RELATION = "parent"


def project_exists(db: Session, project_id: str) -> bool:
    return db.get(Project, project_id) is not None


async def create_project(db: Session, auth: AuthorizationService, payload: ProjectCreate) -> ProjectRead:
    if db.get(Client, payload.client_id) is None:
        raise ResourceNotFoundError("client", payload.client_id)

    project = Project(id=payload.id, client_id=payload.client_id, name=payload.name)
    db.add(project)
    audit_service.record_event(
        db,
        event_type="project.created",
        resource_type="project",
        resource_id=payload.id,
        action="create",
        result="success",
        event_metadata={"name": payload.name, "client_id": payload.client_id},
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateResourceError("project", "id", payload.id) from exc

    db.refresh(project)

    try:
        await auth.write_tuple(
            user=f"{CLIENT_TYPE}:{payload.client_id}",
            relation=PARENT_RELATION,
            object=f"{PROJECT_TYPE}:{payload.id}",
        )
    except AuthorizationServiceUnavailableError:
        logger.error(
            "OpenFGA write failed after project %r was committed; rolling back the business row", payload.id
        )
        db.delete(project)
        db.query(AuditEvent).filter(
            AuditEvent.resource_type == "project",
            AuditEvent.resource_id == payload.id,
            AuditEvent.event_type == "project.created",
        ).delete(synchronize_session=False)
        db.commit()
        raise

    return ProjectRead.model_validate(project)


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError("project", project_id)
    return project


def list_projects(db: Session) -> list[Project]:
    return list(db.query(Project).order_by(Project.created_at).all())
