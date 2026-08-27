from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import Project, ProjectMember, User

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise CREDENTIALS_ERROR
    subject = decode_access_token(creds.credentials)
    if subject is None:
        raise CREDENTIALS_ERROR
    user = db.query(User).filter(User.id == int(subject)).first()
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


def get_project_or_404(project_id: int, db: Session, user: User) -> Project:
    """Return the project if the user can see it, else raise 404/403."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not user_can_view(project, user, db):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    return project


def user_can_view(project: Project, user: User, db: Session) -> bool:
    if project.owner_id == user.id:
        return True
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .first()
        is not None
    )


def user_can_edit(project: Project, user: User, db: Session) -> bool:
    if project.owner_id == user.id:
        return True
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .first()
    )
    return membership is not None and membership.role in {"owner", "admin", "member"}


def require_edit(project: Project, user: User, db: Session) -> None:
    if not user_can_edit(project, user, db):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this project")


def require_admin(project: Project, user: User, db: Session) -> None:
    if project.owner_id == user.id:
        return
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .first()
    )
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Admin permission required")
