"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, verify_password
from app.database import get_db
from app.models import NGO, Institution, User
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_payload(db: Session, user: User) -> dict:
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    ngo = db.get(NGO, user.ngo_id) if user.ngo_id else None
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name,
        "role": user.role, "phone": user.phone,
        "institution": {"id": inst.id, "name": inst.name, "segment": inst.segment}
        if inst else None,
        "ngo": {"id": ngo.id, "name": ngo.name} if ngo else None,
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    if not user.active:
        raise HTTPException(403, "Account is deactivated")
    return TokenResponse(access_token=create_access_token(user),
                         user=_user_payload(db, user))


@router.post("/token", response_model=TokenResponse)
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 form-encoded variant so Swagger's Authorize button works."""
    return login(LoginRequest(email=form.username, password=form.password), db)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_payload(db, user)


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Convenience endpoint for the demo login screen."""
    out = []
    for role, pwd in [("super_admin", "admin123"), ("kitchen_manager", "kitchen123"),
                      ("coordinator", "coord123"), ("ngo_partner", "ngo123"),
                      ("customer", "user123")]:
        for u in db.query(User).filter(User.role == role).limit(3).all():
            inst = db.get(Institution, u.institution_id) if u.institution_id else None
            out.append({"email": u.email, "password": pwd, "role": role,
                        "full_name": u.full_name,
                        "institution": inst.name if inst else None})
    return out
