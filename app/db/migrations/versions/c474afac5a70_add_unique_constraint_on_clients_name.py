"""add unique constraint on clients.name

Revision ID: c474afac5a70
Revises: 1c343d3715e0
Create Date: 2026-09-10 23:05:28.678516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c474afac5a70'
down_revision: Union[str, Sequence[str], None] = '1c343d3715e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint("uq_clients_name", "clients", ["name"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_clients_name", "clients", type_="unique")
