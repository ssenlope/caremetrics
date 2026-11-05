"""add claims indexes

Revision ID: 7bec72067828
Revises: e3d3d507e4a2
Create Date: 2026-11-04 23:56:54.669089

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bec72067828'
down_revision: Union[str, None] = 'e3d3d507e4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_claims_npi_service_date", "claims", ["npi", "service_date"])
    op.create_index("ix_claims_service_date", "claims", ["service_date"])


def downgrade() -> None:
    op.drop_index("ix_claims_service_date", table_name="claims")
    op.drop_index("ix_claims_npi_service_date", table_name="claims")
