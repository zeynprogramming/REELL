"""Phase 6: worker-owned fields on processing_jobs.

Revision ID: 0004_phase6_jobs
Revises: 0003_phase5_files
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_phase6_jobs"
down_revision = "0003_phase5_files"
branch_labels = None
depends_on = None

def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("processing_jobs")}
    if "started_at" not in existing:
        op.add_column("processing_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    if "finished_at" not in existing:
        op.add_column("processing_jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    if "attempts" not in existing:
        op.add_column("processing_jobs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    if "result" not in existing:
        op.add_column("processing_jobs", sa.Column("result", sa.JSON(), nullable=True))

def downgrade():
    for column in ("result", "attempts", "finished_at", "started_at"):
        op.drop_column("processing_jobs", column)
