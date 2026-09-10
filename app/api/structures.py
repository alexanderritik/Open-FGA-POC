from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService, get_authorization_service
from app.db.database import get_db
from app.schemas.structure import StructureCreate, StructureListItem, StructureRead
from app.services import structure_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError

router = APIRouter(prefix="/structures", tags=["structures"])


@router.post(
    "",
    response_model=StructureRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a structure under a zone",
    responses={
        404: {"description": "Parent zone does not exist"},
        409: {"description": "A structure with this id already exists"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def create_structure(
    payload: StructureCreate,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> StructureRead:
    try:
        return await structure_service.create_structure(db, auth, payload)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("", response_model=list[StructureListItem], summary="List structures (business data only)")
def list_structures(db: Session = Depends(get_db)) -> list[StructureListItem]:
    structures = structure_service.list_structures(db)
    return [StructureListItem.model_validate(s) for s in structures]


@router.get(
    "/{structure_id}",
    response_model=StructureRead,
    summary="Get a structure, including its OpenFGA-recorded parent zone",
    responses={404: {"description": "Structure not found"}, 503: {"description": "Authorization engine unavailable"}},
)
async def get_structure(
    structure_id: str,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> StructureRead:
    try:
        return await structure_service.get_structure(db, auth, structure_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
