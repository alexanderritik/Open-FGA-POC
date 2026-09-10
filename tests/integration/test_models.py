import pytest
from sqlalchemy import inspect

from app.db.database import SessionLocal, engine
from app.db.models import AuditEvent, Client, Project, Structure, User


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def test_no_zones_table_exists():
    table_names = inspect(engine).get_table_names()
    assert "zones" not in table_names


def test_structures_table_has_no_zone_column():
    columns = {c["name"] for c in inspect(engine).get_columns("structures")}
    assert "zone_id" not in columns
    assert "parent_zone_id" not in columns


def test_create_client_project_structure_and_audit_event(db_session):
    client = Client(id="govt-of-india", name="Govt of India")
    db_session.add(client)
    db_session.flush()

    project = Project(id="indian-railway", client_id=client.id, name="Indian Railway")
    db_session.add(project)
    db_session.flush()

    structure = Structure(id="yamuna-bridge", name="Yamuna Bridge")
    db_session.add(structure)
    db_session.flush()

    user = User(id="parth", name="Parth")
    db_session.add(user)
    db_session.flush()

    event = AuditEvent(
        event_type="structure.created",
        actor="user:parth",
        resource_type="structure",
        resource_id="yamuna-bridge",
        action="create",
        result="success",
        event_metadata={"parent_zone_id": "central"},
    )
    db_session.add(event)
    db_session.flush()

    assert db_session.query(Project).filter_by(id="indian-railway").one().client_id == "govt-of-india"
    assert db_session.query(AuditEvent).filter_by(resource_id="yamuna-bridge").one().event_metadata == {
        "parent_zone_id": "central"
    }
