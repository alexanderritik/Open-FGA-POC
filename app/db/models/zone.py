from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Zone(Base):
    """Metadata mirror for a Zone: `name`, plus a copy of the parent
    reference OpenFGA already tracks.

    OpenFGA (app/authorization/service.py) remains the sole source of truth
    for the zone hierarchy: it is authoritative for existence, cycle
    detection, and every authorization/tree-traversal decision. This table
    exists only because a zone's `name` has nowhere else to live and
    OpenFGA tuples aren't queryable that way. `parent_id` deliberately has
    no foreign key — depending on `parent_type` it references either
    `projects.id` or another row in this same table (zones nest to
    arbitrary depth), and OpenFGA is what actually enforces that shape.
    """

    __tablename__ = "zones"
    __table_args__ = (Index("ix_zones_parent", "parent_type", "parent_id"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
