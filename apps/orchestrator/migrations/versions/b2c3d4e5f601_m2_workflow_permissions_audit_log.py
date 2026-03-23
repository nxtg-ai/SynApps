"""M-2: add workflow_permissions, audit_log_entries tables

Revision ID: b2c3d4e5f601
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f601"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workflow_permissions and audit_log_entries tables."""
    op.create_table(
        "workflow_permissions",
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("grants", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("flow_id"),
    )

    op.create_table(
        "audit_log_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_entries_timestamp", "audit_log_entries", ["timestamp"])
    op.create_index("ix_audit_log_entries_actor", "audit_log_entries", ["actor"])
    op.create_index(
        "ix_audit_log_entries_resource",
        "audit_log_entries",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    """Drop workflow_permissions and audit_log_entries tables."""
    op.drop_index("ix_audit_log_entries_resource", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_actor", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_timestamp", table_name="audit_log_entries")
    op.drop_table("audit_log_entries")
    op.drop_table("workflow_permissions")
