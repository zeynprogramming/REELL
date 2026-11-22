"""Phase 7-8: edit projects and export jobs.

Revision ID: 0006_edit_projects
Revises: 0005_manual_workspace
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_edit_projects"
down_revision = "0005_manual_workspace"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "edit_projects" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "edit_projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("timeline_json", sa.Text(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_edit_projects_id", "edit_projects", ["id"])
    existing = {c["name"] for c in sa.inspect(bind).get_columns("processing_jobs")}
    if "project_id" not in existing:
        with op.batch_alter_table("processing_jobs") as batch:
            batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_jobs_project", "edit_projects", ["project_id"], ["id"], ondelete="CASCADE")
            batch.create_index("ix_processing_jobs_project_id", ["project_id"])
    if "params" not in existing:
        op.add_column("processing_jobs", sa.Column("params", sa.JSON(), nullable=True))

def downgrade():
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_index("ix_processing_jobs_project_id")
        batch.drop_constraint("fk_jobs_project", type_="foreignkey")
        batch.drop_column("project_id")
        batch.drop_column("params")
    op.drop_table("edit_projects")
