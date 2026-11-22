import logging
import os
from sqlalchemy import func
from .database import SessionLocal
from . import models
from .security import MIN_PASSWORD_LENGTH, hash_password

log = logging.getLogger("reel.bootstrap")

def bootstrap_admin() -> None:
    """Create the first administrator from env vars, only when the users table is empty."""
    with SessionLocal() as db:
        if (db.query(func.count(models.User.id)).scalar() or 0) > 0:
            return
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        if not email or not password:
            log.warning("No users exist. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD, then restart the API.")
            return
        if len(password) < MIN_PASSWORD_LENGTH:
            raise RuntimeError(f"BOOTSTRAP_ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters.")
        db.add(models.User(
            email=email,
            full_name=os.getenv("BOOTSTRAP_ADMIN_NAME", "REEL Admin"),
            password_hash=hash_password(password),
            role="admin",
        ))
        db.commit()
        log.info("Created the initial administrator account for %s.", email)
