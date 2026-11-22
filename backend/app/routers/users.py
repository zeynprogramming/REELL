from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .. import audit, models, schemas
from ..auth import require_admin
from ..database import get_db
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["Users"], dependencies=[Depends(require_admin)])
audit_router = APIRouter(prefix="/api/audit-logs", tags=["Audit Log"], dependencies=[Depends(require_admin)])

@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.created_at.asc(), models.User.id.asc()).all()

@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, request: Request, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists.")
    user = models.User(email=payload.email, full_name=payload.full_name, role=payload.role, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists.")
    db.refresh(user)
    audit.record(db, "user_created", request, user_id=admin.id, detail=f"user_id={user.id} role={user.role}")
    return user

@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, payload: schemas.UserUpdate, request: Request, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        ("role" in changes and changes["role"] != user.role)
        or ("is_active" in changes and changes["is_active"] is False)
    ):
        # Also guarantees at least one active administrator always remains.
        raise HTTPException(status_code=400, detail="You cannot change your own role or deactivate your own account.")
    invalidate = False
    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"].strip() or user.full_name
    if "role" in changes and changes["role"] is not None and changes["role"] != user.role:
        user.role = changes["role"]; invalidate = True
    if "is_active" in changes and changes["is_active"] is not None and changes["is_active"] != user.is_active:
        user.is_active = changes["is_active"]; invalidate = True
    if changes.get("new_password"):
        user.password_hash = hash_password(changes["new_password"]); invalidate = True
    if invalidate:
        user.token_version += 1
    db.commit()
    db.refresh(user)
    audit.record(db, "user_updated", request, user_id=admin.id, detail=f"user_id={user.id} fields={','.join(sorted(k for k in changes if k != 'new_password')) or '-'}{' password_reset' if changes.get('new_password') else ''}")
    return user

@audit_router.get("", response_model=list[schemas.AuditLogOut])
def list_audit_logs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc()).offset(offset).limit(limit).all()
