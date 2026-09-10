import uuid

import pytest
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models.audit_event import AuditEvent
from app.db.models.client import Client
from app.schemas.client import ClientCreate
from app.services import client_service
from app.services.exceptions import DuplicateResourceError, ResourceNotFoundError


@pytest.fixture
def db_session():
    session = SessionLocal()
    created_ids: list[str] = []
    try:
        yield session, created_ids
    finally:
        if created_ids:
            session.query(AuditEvent).filter(AuditEvent.resource_id.in_(created_ids)).delete(
                synchronize_session=False
            )
            session.query(Client).filter(Client.id.in_(created_ids)).delete(synchronize_session=False)
            session.commit()
        session.close()


def unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_create_client_persists_row_and_audit_event(db_session):
    session, created_ids = db_session
    client_id = unique_id("test-client")
    created_ids.append(client_id)

    client = client_service.create_client(session, ClientCreate(id=client_id, name=f"Name {client_id}"))

    assert client.id == client_id
    assert client.created_at is not None

    stored = session.get(Client, client_id)
    assert stored is not None
    assert stored.name == f"Name {client_id}"

    event = session.scalars(
        select(AuditEvent).where(AuditEvent.resource_id == client_id, AuditEvent.event_type == "client.created")
    ).one()
    assert event.actor == "system"
    assert event.result == "success"
    assert event.event_metadata == {"name": f"Name {client_id}"}


def test_create_client_duplicate_id_raises_and_rolls_back(db_session):
    session, created_ids = db_session
    client_id = unique_id("test-client")
    created_ids.append(client_id)

    client_service.create_client(session, ClientCreate(id=client_id, name=f"Name {client_id}"))

    with pytest.raises(DuplicateResourceError) as exc_info:
        client_service.create_client(session, ClientCreate(id=client_id, name="Some Other Name"))
    assert exc_info.value.field == "id"

    # The failed attempt must not have left a second audit event behind.
    events = session.scalars(select(AuditEvent).where(AuditEvent.resource_id == client_id)).all()
    assert len(events) == 1


def test_create_client_duplicate_name_raises(db_session):
    session, created_ids = db_session
    name = f"Shared Name {uuid.uuid4().hex[:8]}"
    first_id = unique_id("test-client")
    second_id = unique_id("test-client")
    created_ids.extend([first_id, second_id])

    client_service.create_client(session, ClientCreate(id=first_id, name=name))

    with pytest.raises(DuplicateResourceError) as exc_info:
        client_service.create_client(session, ClientCreate(id=second_id, name=name))
    assert exc_info.value.field == "name"

    assert session.get(Client, second_id) is None


def test_get_client_not_found_raises(db_session):
    session, _ = db_session
    with pytest.raises(ResourceNotFoundError):
        client_service.get_client(session, "does-not-exist")


def test_list_clients_includes_created(db_session):
    session, created_ids = db_session
    client_id = unique_id("test-client")
    created_ids.append(client_id)
    client_service.create_client(session, ClientCreate(id=client_id, name=f"Name {client_id}"))

    clients = client_service.list_clients(session)
    assert any(c.id == client_id for c in clients)
