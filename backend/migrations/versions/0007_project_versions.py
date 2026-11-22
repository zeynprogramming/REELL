"""Phase 13: project version history.

Revision ID: 0007_project_versions
Revises: 0006_edit_projects
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_project_versions"
down_revision = "0006_edit_projects"
branch_labels = None
depends_on = None

def upgrade():
    if "project_versions" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "project_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("edit_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("label", sa.String(60), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("timeline_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_project_versions_id", "project_versions", ["id"])
        op.create_index("ix_project_versions_project_id", "project_versions", ["project_id"])

def downgrade():
    op.drop_table("project_versions")
