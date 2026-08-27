"""Directory of active users — powers assignee/member pickers and the Team page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import UserPublic

router = APIRouter(prefix="", tags=["users"])


@router.get("/users", response_model=list[UserPublic])
def list_users(
    q: str | None = Query(default=None, description="Match full name or email"),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    query = db.query(User).filter(User.is_active.is_(True))
    term = (q or "").strip()
    if term:
        pattern = f"%{term.lower()}%"
        query = query.filter(
            or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )
    return query.order_by(func.lower(User.full_name).asc(), User.id.asc()).limit(limit).all()


@router.get("/users/{user_id}", response_model=UserPublic)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
