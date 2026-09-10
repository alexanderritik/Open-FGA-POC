from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Project(Base):
    """Business record for a Project. Belongs to a Client in this database;
    the `project:<id>#parent@client:<client_id>` OpenFGA tuple is written
    separately by the authorization service to establish the authorization
    hierarchy."""

    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_client_id", "client_id"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    client: Mapped["Client"] = relationship(back_populates="projects")
