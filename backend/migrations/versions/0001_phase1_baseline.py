"""Adopt the Phase 1 schema under Alembic management.

Revision ID: 0001_phase1_baseline
Revises:
"""
import sqlalchemy as sa
from alembic import op
from app.database import Base
from app import models

revision = "0001_phase1_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Only the Phase 1 tables belong to this revision. Later tables are created by their own revisions.
PHASE1_TABLES = [
    models.Recording.__table__,
    models.Transcript.__table__,
    models.VideoMetadata.__table__,
    models.PublishedVideo.__table__,
    models.Integration.__table__,
    models.StudentConsent.__table__,
]

def upgrade():
    bind = op.get_bind()
    # checkfirst=True safely adopts databases whose tables were created in Phase 1.
    Base.metadata.create_all(bind=bind, tables=PHASE1_TABLES, checkfirst=True)
    # processing_jobs is written out by hand with its Phase 1 columns only. The current model also points to edit_projects
    # (added later, revision 0006), which does not exist yet on a fresh database; revisions 0004 and 0006 add the rest.
    if "processing_jobs" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "processing_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True),
            sa.Column("job_type", sa.String(80), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_processing_jobs_id", "processing_jobs", ["id"])
        op.create_index("ix_processing_jobs_recording_id", "processing_jobs", ["recording_id"])
        op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
        op.create_index("ix_jobs_status_created", "processing_jobs", ["status", "created_at"])

def downgrade():
    # Baseline downgrade intentionally preserves user data and existing tables.
    pass
