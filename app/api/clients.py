from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.client import ClientCreate, ClientRead
from app.services import client_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post(
    "",
    response_model=ClientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a client",
    responses={409: {"description": "A client with this id or name already exists"}},
)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> ClientRead:
    try:
        client = client_service.create_client(db, payload)
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ClientRead.model_validate(client)


@router.get("", response_model=list[ClientRead], summary="List clients")
def list_clients(db: Session = Depends(get_db)) -> list[ClientRead]:
    clients = client_service.list_clients(db)
    return [ClientRead.model_validate(c) for c in clients]


@router.get(
    "/{client_id}",
    response_model=ClientRead,
    summary="Get a client by id",
    responses={404: {"description": "Client not found"}},
)
def get_client(client_id: str, db: Session = Depends(get_db)) -> ClientRead:
    try:
        client = client_service.get_client(db, client_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ClientRead.model_validate(client)
