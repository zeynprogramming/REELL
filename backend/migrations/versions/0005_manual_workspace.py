"""Manual workspace: tags on video_metadata.

Revision ID: 0005_manual_workspace
Revises: 0004_phase6_jobs
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_manual_workspace"
down_revision = "0004_phase6_jobs"
branch_labels = None
depends_on = None

def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("video_metadata")}
    if "tags_json" not in existing:
        op.add_column("video_metadata", sa.Column("tags_json", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("video_metadata", "tags_json")
