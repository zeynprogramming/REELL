"""FastAPI dependencies for authentication and role-based access (Phase 4)."""
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from . import models
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_ROLES = {"admin", "editor"}

def _unauthorized(detail: str = "Not authenticated.") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized("Session expired or invalid. Please sign in again.")
    user = db.get(models.User, user_id)
    if user is None or not user.is_active or payload.get("tv") != user.token_version:
        raise _unauthorized("Session expired or invalid. Please sign in again.")
    return user

def require_write_access(request: Request, user: models.User = Depends(get_current_user)) -> models.User:
    """Any signed-in user may read; only admins and editors may create, change or delete."""
    if request.method not in SAFE_METHODS and user.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Your role is read-only and cannot change data.")
    return user

def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user
