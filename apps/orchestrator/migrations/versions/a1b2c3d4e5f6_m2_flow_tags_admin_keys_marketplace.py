"""M-2: add flow_tags, admin_keys, marketplace_listings tables

Revision ID: a1b2c3d4e5f6
Revises: fd07f894a915
Create Date: 2026-03-22 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "8e8ca3c65593"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create flow_tags, admin_keys, and marketplace_listings tables."""
    op.create_table(
        "flow_tags",
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["flow_id"], ["flows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("flow_id", "tag"),
    )

    op.create_table(
        "admin_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("last_used_at", sa.Float(), nullable=True),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_keys_key_prefix", "admin_keys", ["key_prefix"])

    op.create_table(
        "marketplace_listings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("author", sa.String(), nullable=False, server_default="anonymous"),
        sa.Column("publisher_id", sa.String(), nullable=True),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("edges", sa.JSON(), nullable=False),
        sa.Column("install_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("install_timestamps", sa.JSON(), nullable=False),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.Float(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["publisher_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_listings_name", "marketplace_listings", ["name"])
    op.create_index("ix_marketplace_listings_category", "marketplace_listings", ["category"])


def downgrade() -> None:
    """Drop flow_tags, admin_keys, and marketplace_listings tables."""
    op.drop_index("ix_marketplace_listings_category", table_name="marketplace_listings")
    op.drop_index("ix_marketplace_listings_name", table_name="marketplace_listings")
    op.drop_table("marketplace_listings")
    op.drop_index("ix_admin_keys_key_prefix", table_name="admin_keys")
    op.drop_table("admin_keys")
    op.drop_table("flow_tags")
