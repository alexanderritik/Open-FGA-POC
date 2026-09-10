from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService, get_authorization_service
from app.db.database import get_db
from app.schemas.project import ProjectCreate, ProjectRead
from app.services import project_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project under a client",
    responses={
        404: {"description": "Parent client does not exist"},
        409: {"description": "A project with this id already exists"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> ProjectRead:
    try:
        return await project_service.create_project(db, auth, payload)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("", response_model=list[ProjectRead], summary="List projects")
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = project_service.list_projects(db)
    return [ProjectRead.model_validate(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project by id",
    responses={404: {"description": "Project not found"}},
)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRead:
    try:
        project = project_service.get_project(db, project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProjectRead.model_validate(project)
