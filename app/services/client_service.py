from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.client import Client
from app.schemas.client import ClientCreate
from app.services import audit_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError


def create_client(db: Session, payload: ClientCreate) -> Client:
    client = Client(id=payload.id, name=payload.name)
    db.add(client)
    audit_service.record_event(
        db,
        event_type="client.created",
        resource_type="client",
        resource_id=payload.id,
        action="create",
        result="success",
        event_metadata={"name": payload.name},
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc, payload) from exc

    db.refresh(client)
    return client


def get_client(db: Session, client_id: str) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise ResourceNotFoundError("client", client_id)
    return client


def list_clients(db: Session) -> list[Client]:
    return list(db.query(Client).order_by(Client.created_at).all())


def client_exists(db: Session, client_id: str) -> bool:
    return db.get(Client, client_id) is not None


def _translate_integrity_error(exc: IntegrityError, payload: ClientCreate) -> DuplicateResourceError:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None) or ""
    if constraint == "uq_clients_name":
        return DuplicateResourceError("client", "name", payload.name)
    # Any other integrity violation on this table is the primary key (id).
    return DuplicateResourceError("client", "id", payload.id)
