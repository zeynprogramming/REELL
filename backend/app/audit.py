from fastapi import Request
from sqlalchemy.orm import Session
from . import models

def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

def record(db: Session, action: str, request: Request | None = None, user_id: int | None = None, detail: str | None = None) -> None:
    """Append a security audit entry. Never include passwords or tokens in `detail`."""
    db.add(models.AuditLog(user_id=user_id, action=action, detail=detail, ip_address=client_ip(request) if request else None))
    db.commit()
