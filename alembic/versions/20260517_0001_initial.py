"""Initial FastAPI schema.

Revision ID: 20260517_0001
Revises:
Create Date: 2026-05-17
"""

import sqlalchemy as sa

from alembic import op

revision = "20260517_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("max_file_size", sa.Integer(), nullable=False),
        sa.Column("bump_limit", sa.Integer(), nullable=False),
        sa.Column("max_threads", sa.Integer(), nullable=False),
        sa.Column("max_message_length", sa.Integer(), nullable=False),
        sa.Column("captcha", sa.String(length=32), nullable=False),
        sa.Column("stop_board", sa.Boolean(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("post_id_seed", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "posts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("parent", sa.BigInteger(), nullable=False),
        sa.Column("sage", sa.Boolean(), nullable=False),
        sa.Column("time", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("file1", sa.String(length=255), nullable=True),
        sa.Column("file1_info", sa.String(length=255), nullable=True),
        sa.Column("file2", sa.String(length=255), nullable=True),
        sa.Column("file2_info", sa.String(length=255), nullable=True),
        sa.Column("file3", sa.String(length=255), nullable=True),
        sa.Column("file3_info", sa.String(length=255), nullable=True),
        sa.Column("file4", sa.String(length=255), nullable=True),
        sa.Column("file4_info", sa.String(length=255), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("status_time", sa.BigInteger(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("verify", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_parent", "posts", ["parent"])
    op.create_index("ix_posts_status", "posts", ["status"])
    op.create_index("ix_posts_verify", "posts", ["verify"])
    op.create_index("idx_posts_parent_status", "posts", ["parent", "status"])


def downgrade() -> None:
    op.drop_index("idx_posts_parent_status", table_name="posts")
    op.drop_index("ix_posts_verify", table_name="posts")
    op.drop_index("ix_posts_status", table_name="posts")
    op.drop_index("ix_posts_parent", table_name="posts")
    op.drop_table("posts")
    op.drop_table("options")
