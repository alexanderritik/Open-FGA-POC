from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Structure(Base):
    """Business record for a Structure.

    Deliberately has NO foreign key to a Zone: the `zones` table (see
    app/db/models/zone.py) is a metadata mirror, not the source of truth
    for hierarchy. A structure's parent Zone is recorded exclusively as an
    OpenFGA tuple (`structure:<id>#parent@zone:<zone_id>`), written by the
    authorization service at creation time.
    """

    __tablename__ = "structures"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
