from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .. import audit, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..security import (
    create_access_token, dummy_hash, email_throttle, hash_password, ip_throttle, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def _token_response(user: models.User) -> dict:
    token, expires_in = create_access_token(user.id, user.token_version)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": user}

@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = audit.client_ip(request)
    wait = max(email_throttle.retry_after(payload.email), ip_throttle.retry_after(ip))
    if wait:
        audit.record(db, "login_blocked", request, detail=f"email={payload.email}")
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again later.", headers={"Retry-After": str(wait)})

    user = db.query(models.User).filter(models.User.email == payload.email).first()
    # Always run one hash verification so timing does not reveal whether the email exists.
    password_ok = verify_password(payload.password, user.password_hash if user else dummy_hash())
    if user is None or not password_ok or not user.is_active:
        email_throttle.register_failure(payload.email)
        ip_throttle.register_failure(ip)
        audit.record(db, "login_failed", request, user_id=user.id if user else None, detail=f"email={payload.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password.", headers={"WWW-Authenticate": "Bearer"})

    email_throttle.reset(payload.email)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    audit.record(db, "login_success", request, user_id=user.id)
    return _token_response(user)

@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user

@router.post("/change-password", response_model=schemas.TokenResponse)
def change_password(payload: schemas.ChangePasswordRequest, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        audit.record(db, "password_change_failed", request, user_id=user.id)
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="The new password must be different from the current one.")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1  # signs out every other session
    db.commit()
    audit.record(db, "password_changed", request, user_id=user.id)
    return _token_response(user)
