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


def test_zones_table_is_a_metadata_mirror_only():
    """`zones` exists to store `name` (and a copy of the parent reference)
    but must never become the source of truth for hierarchy: no foreign
    key ties `parent_id` to `projects`/`zones`, since the parent's real
    type/target is validated exclusively through OpenFGA
    (app/services/zone_service.py)."""
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("zones")}
    assert columns == {"id", "name", "parent_type", "parent_id", "created_at"}
    assert inspector.get_foreign_keys("zones") == []


def test_structures_table_has_no_zone_column():
    columns = {c["name"] for c in inspect(engine).get_columns("structures")}
    assert "zone_id" not in columns
    assert "parent_zone_id" not in columns


def test_create_client_project_structure_and_audit_event(db_session):
    # Ids here are test-only (not the demo scenario's real ids, e.g.
    # "govt-of-india" from scripts/seed_demo.py) so this test's uncommitted,
    # rollback-cleaned rows never collide with committed demo data that may
    # already be sitting in the same database.
    client = Client(id="model-test-client", name="Model Test Client")
    db_session.add(client)
    db_session.flush()

    project = Project(id="model-test-project", client_id=client.id, name="Model Test Project")
    db_session.add(project)
    db_session.flush()

    structure = Structure(id="model-test-structure", name="Model Test Structure")
    db_session.add(structure)
    db_session.flush()

    user = User(id="model-test-user", name="Model Test User")
    db_session.add(user)
    db_session.flush()

    event = AuditEvent(
        event_type="structure.created",
        actor="user:model-test-user",
        resource_type="structure",
        resource_id="model-test-structure",
        action="create",
        result="success",
        event_metadata={"parent_zone_id": "model-test-zone"},
    )
    db_session.add(event)
    db_session.flush()

    assert db_session.query(Project).filter_by(id="model-test-project").one().client_id == "model-test-client"
    assert db_session.query(AuditEvent).filter_by(resource_id="model-test-structure").one().event_metadata == {
        "parent_zone_id": "model-test-zone"
    }
