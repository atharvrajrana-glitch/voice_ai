"""make session timestamps timezone aware

Revision ID: d9e5f2a1b7c4
Revises: cc13a433a26d
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "d9e5f2a1b7c4"
down_revision = "cc13a433a26d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column_name in ("created_at", "last_activity_at", "expires_at"):
        op.alter_column(
            "patient_sessions",
            column_name,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
            existing_nullable=False,
        )


def downgrade() -> None:
    for column_name in ("created_at", "last_activity_at", "expires_at"):
        op.alter_column(
            "patient_sessions",
            column_name,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
            existing_nullable=False,
        )
