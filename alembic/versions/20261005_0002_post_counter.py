"""Initialize the atomic post counter for existing boards.

Revision ID: 20261005_0002
Revises: 20260517_0001
"""

from alembic import op

revision = "20261005_0002"
down_revision = "20260517_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve both imported post IDs and the administrator's starting offset.
    op.execute("""
        UPDATE options
        SET post_id_seed = CASE
            WHEN post_id_seed > COALESCE((SELECT MAX(id) FROM posts), 0)
            THEN post_id_seed
            ELSE COALESCE((SELECT MAX(id) FROM posts), 0)
        END
    """)


def downgrade() -> None:
    # Older versions can safely use the last issued ID as their starting offset.
    pass
