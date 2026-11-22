"""Phase 5: file metadata columns on recordings.

Revision ID: 0003_phase5_files
Revises: 0002_phase4_auth
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_phase5_files"
down_revision = "0002_phase4_auth"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("recordings")}
    # Guarded: a fresh database may already have these columns from the baseline's create_all.
    if "file_size_bytes" not in existing:
        op.add_column("recordings", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    if "content_type" not in existing:
        op.add_column("recordings", sa.Column("content_type", sa.String(120), nullable=True))
    if "checksum_sha256" not in existing:
        op.add_column("recordings", sa.Column("checksum_sha256", sa.String(64), nullable=True))
        op.create_index("ix_recordings_checksum_sha256", "recordings", ["checksum_sha256"])

def downgrade():
    op.drop_index("ix_recordings_checksum_sha256", table_name="recordings")
    op.drop_column("recordings", "checksum_sha256")
    op.drop_column("recordings", "content_type")
    op.drop_column("recordings", "file_size_bytes")
