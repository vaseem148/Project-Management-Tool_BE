"""Registration, login and current-user endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserPublic, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])

AVATAR_COLORS = [
    "violet",
    "indigo",
    "sky",
    "cyan",
    "emerald",
    "amber",
    "orange",
    "rose",
    "pink",
]

# The frontend palette also offers a neutral option.
ALLOWED_AVATAR_COLORS = set(AVATAR_COLORS) | {"slate"}


def _find_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()


def _next_avatar_color(db: Session) -> str:
    count = db.query(func.count(User.id)).scalar() or 0
    return AVATAR_COLORS[count % len(AVATAR_COLORS)]


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
        user=UserPublic.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.strip().lower()
    if _find_by_email(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        job_title=(payload.job_title or "Team Member").strip() or "Team Member",
        avatar_color=_next_avatar_color(db),
        bio="",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = _find_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled")
    return _token_response(user)


@router.get("/me", response_model=UserPublic)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data:
        full_name = (data["full_name"] or "").strip()
        if len(full_name) < 2:
            raise HTTPException(status_code=422, detail="Name must be at least 2 characters")
        data["full_name"] = full_name
    if "avatar_color" in data and data["avatar_color"] not in ALLOWED_AVATAR_COLORS:
        raise HTTPException(status_code=422, detail="Unsupported avatar color")

    for field, value in data.items():
        setattr(current_user, field, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
