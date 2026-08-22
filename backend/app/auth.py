"""Authentication, password hashing and role-based access control."""
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import JWT_ALGORITHM, JWT_EXPIRY_MINUTES, JWT_SECRET
from app.database import get_db
from app.models import User

# pbkdf2_sha256 is pure-Python: no native bcrypt version pinning to break the
# build the night before a demo. Swap to bcrypt in production if desired.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ROLES = ["super_admin", "kitchen_manager", "coordinator", "ngo_partner", "customer"]


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "institution_id": user.institution_id,
        "ngo_id": user.ngo_id,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.get(User, int(user_id))
    if user is None or not user.active:
        raise credentials_error
    return user


def require_roles(*allowed: str):
    """Dependency factory enforcing that the caller holds one of `allowed`."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted to access this resource",
            )
        return user

    return _guard


def scoped_institution_id(user: User, requested: int | None = None) -> int:
    """Resolve which institution a caller may act on.

    Super admins may target any institution; everyone else is pinned to their
    own, which is what makes this multi-tenant rather than merely multi-user.
    """
    if user.role == "super_admin":
        if requested is None:
            raise HTTPException(400, "super_admin must specify institution_id")
        return requested
    if user.institution_id is None:
        raise HTTPException(400, "User is not attached to an institution")
    if requested is not None and requested != user.institution_id:
        raise HTTPException(403, "Cross-institution access denied")
    return user.institution_id
