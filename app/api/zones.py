from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService, get_authorization_service
from app.db.database import get_db
from app.schemas.zone import ZoneChildren, ZoneCreate, ZoneRead
from app.services import zone_service
from app.services.exceptions import CircularReferenceError, DuplicateResourceError, ResourceNotFoundError

router = APIRouter(tags=["zones"])


@router.post(
    "/zones",
    response_model=ZoneRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a zone under a project or another zone",
    responses={
        404: {"description": "Parent project/zone does not exist"},
        409: {"description": "A zone with this id already exists under a different parent"},
        422: {"description": "Invalid request, or would create a circular zone relationship"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def create_zone(
    payload: ZoneCreate,
    response: Response,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> ZoneRead:
    try:
        zone, created = await zone_service.create_zone(db, auth, payload)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CircularReferenceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    return zone


@router.get(
    "/zones/{zone_id}",
    response_model=ZoneRead,
    summary="Get a zone's immediate parent",
    responses={404: {"description": "Zone not found"}, 503: {"description": "Authorization engine unavailable"}},
)
async def get_zone(
    zone_id: str,
    auth: AuthorizationService = Depends(get_authorization_service),
) -> ZoneRead:
    try:
        return await zone_service.get_zone(auth, zone_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/zones/{zone_id}/children",
    response_model=ZoneChildren,
    summary="List a zone's immediate child zones and structures",
    responses={404: {"description": "Zone not found"}, 503: {"description": "Authorization engine unavailable"}},
)
async def get_zone_children(
    zone_id: str,
    auth: AuthorizationService = Depends(get_authorization_service),
) -> ZoneChildren:
    try:
        return await zone_service.get_zone_children(auth, zone_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/zones",
    response_model=list[ZoneRead],
    summary="List a project's immediate child zones",
    responses={404: {"description": "Project not found"}, 503: {"description": "Authorization engine unavailable"}},
)
async def list_project_zones(
    project_id: str,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> list[ZoneRead]:
    try:
        return await zone_service.list_zones_under_project(db, auth, project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
