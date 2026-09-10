from sqlalchemy.orm import Session

from app.db.models.project import Project

# Full Project CRUD endpoints are not built yet (out of scope for the Zone
# API step). Zone creation needs to validate that a referenced parent
# project exists, so only that minimal existence check lives here for now.


def project_exists(db: Session, project_id: str) -> bool:
    return db.get(Project, project_id) is not None
