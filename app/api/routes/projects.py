"""Project, member and label endpoints."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    get_current_user,
    get_project_or_404,
    require_admin,
    require_edit,
)
from app.core.database import get_db
from app.models import Label, Project, ProjectMember, User, task_labels
from app.schemas import (
    LabelCreate,
    LabelPublic,
    MemberCreate,
    MemberPublic,
    MemberUpdate,
    Message,
    ProjectCreate,
    ProjectPublic,
    ProjectStats,
    ProjectStatus,
    ProjectUpdate,
)
from app.services.serializers import (
    compute_project_stats,
    log_activity,
    serialize_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])
# DELETE /api/labels/{label_id} lives here too — main.py includes both routers.
label_router = APIRouter(prefix="/labels", tags=["projects"])

DEFAULT_LABELS: tuple[tuple[str, str], ...] = (
    ("Bug", "rose"),
    ("Feature", "violet"),
    ("Design", "cyan"),
    ("Docs", "amber"),
)

KEY_MAX_LENGTH = 10


def _generate_key(db: Session, name: str, requested: str | None = None) -> str:
    """Build a short unique project key: word initials, else the first letters of the name."""
    if requested:
        base = re.sub(r"[^A-Za-z0-9]", "", requested).upper()[:KEY_MAX_LENGTH]
    else:
        words = re.findall(r"[A-Za-z0-9]+", name)
        base = "".join(word[0] for word in words).upper()[:4]
        if len(base) < 2:
            base = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:3]
    if not base:
        base = "PRJ"

    candidate = base
    suffix = 2
    while db.query(Project.id).filter(Project.key == candidate).first() is not None:
        tail = str(suffix)
        candidate = f"{base[: KEY_MAX_LENGTH - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _project_query(db: Session, user: User):
    """Projects the user owns or is a member of, without duplicates."""
    member_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    return (
        db.query(Project)
        .options(
            selectinload(Project.owner),
            selectinload(Project.members).selectinload(ProjectMember.user),
        )
        .filter(or_(Project.owner_id == user.id, Project.id.in_(member_project_ids)))
    )


def _get_member_or_404(db: Session, project_id: int, user_id: int) -> ProjectMember:
    member = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found in this project")
    return member


# --------------------------------------------------------------------- projects
@router.get("", response_model=list[ProjectPublic])
def list_projects(
    q: str | None = Query(default=None, max_length=160),
    status: ProjectStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectPublic]:
    query = _project_query(db, user)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(Project.name.ilike(needle), Project.description.ilike(needle)))
    if status:
        query = query.filter(Project.status == status)
    projects = query.order_by(Project.created_at.desc(), Project.id.desc()).all()
    return [serialize_project(db, project) for project in projects]


@router.post("", response_model=ProjectPublic, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectPublic:
    project = Project(
        key=_generate_key(db, payload.name, payload.key),
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        color=payload.color,
        status=payload.status,
        start_date=payload.start_date,
        due_date=payload.due_date,
        owner_id=user.id,
    )
    db.add(project)
    db.flush()

    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))

    member_ids = [uid for uid in dict.fromkeys(payload.member_ids) if uid != user.id]
    if member_ids:
        existing_ids = {
            row_id
            for (row_id,) in db.query(User.id)
            .filter(User.id.in_(member_ids), User.is_active.is_(True))
            .all()
        }
        for user_id in member_ids:
            if user_id in existing_ids:
                db.add(ProjectMember(project_id=project.id, user_id=user_id, role="member"))

    for label_name, label_color in DEFAULT_LABELS:
        db.add(Label(project_id=project.id, name=label_name, color=label_color))

    log_activity(
        db,
        actor=user,
        action="project_created",
        summary=f"created project {project.name}",
        project_id=project.id,
        meta={"key": project.key},
    )

    db.commit()
    db.refresh(project)
    return serialize_project(db, project)


@router.get("/{project_id}", response_model=ProjectPublic)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectPublic:
    project = get_project_or_404(project_id, db, user)
    return serialize_project(db, project)


@router.patch("/{project_id}", response_model=ProjectPublic)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectPublic:
    project = get_project_or_404(project_id, db, user)
    require_admin(project, user, db)

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("name"):
        changes["name"] = changes["name"].strip()
    for field, value in changes.items():
        setattr(project, field, value)

    if changes:
        log_activity(
            db,
            actor=user,
            action="project_updated",
            summary=f"updated {', '.join(sorted(changes))} on {project.name}",
            project_id=project.id,
            meta={"fields": sorted(changes)},
        )

    db.commit()
    db.refresh(project)
    return serialize_project(db, project)


@router.delete("/{project_id}", response_model=Message)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    project = get_project_or_404(project_id, db, user)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can delete this project")

    name = project.name
    # Stored without a project link so the entry survives the cascade.
    log_activity(
        db,
        actor=user,
        action="project_deleted",
        summary=f"deleted project {name}",
        meta={"key": project.key, "name": name},
    )
    db.delete(project)
    db.commit()
    return Message(detail=f"Project {name} deleted")


@router.get("/{project_id}/stats", response_model=ProjectStats)
def project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectStats:
    project = get_project_or_404(project_id, db, user)
    return compute_project_stats(db, project)


# ---------------------------------------------------------------------- members
@router.get("/{project_id}/members", response_model=list[MemberPublic])
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectMember]:
    get_project_or_404(project_id, db, user)
    return (
        db.query(ProjectMember)
        .options(selectinload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at.asc(), ProjectMember.id.asc())
        .all()
    )


@router.post("/{project_id}/members", response_model=MemberPublic, status_code=201)
def add_member(
    project_id: int,
    payload: MemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMember:
    project = get_project_or_404(project_id, db, user)
    require_admin(project, user, db)

    target = db.query(User).filter(User.id == payload.user_id, User.is_active.is_(True)).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    duplicate = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == target.id)
        .first()
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This user is already a member of the project")

    role = "owner" if target.id == project.owner_id else payload.role
    member = ProjectMember(project_id=project.id, user_id=target.id, role=role)
    db.add(member)
    log_activity(
        db,
        actor=user,
        action="member_added",
        summary=f"added {target.full_name} to {project.name}",
        project_id=project.id,
        meta={"user_id": target.id, "role": role},
    )
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{project_id}/members/{user_id}", response_model=MemberPublic)
def update_member(
    project_id: int,
    user_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMember:
    project = get_project_or_404(project_id, db, user)
    require_admin(project, user, db)

    member = _get_member_or_404(db, project.id, user_id)
    if member.user_id == project.owner_id and payload.role != "owner":
        raise HTTPException(status_code=400, detail="The role of the project owner cannot be changed")

    member.role = payload.role
    member_name = member.user.full_name if member.user else "a member"
    log_activity(
        db,
        actor=user,
        action="member_updated",
        summary=f"changed {member_name} to {payload.role} on {project.name}",
        project_id=project.id,
        meta={"user_id": member.user_id, "role": payload.role},
    )
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{project_id}/members/{user_id}", response_model=Message)
def remove_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    project = get_project_or_404(project_id, db, user)
    require_admin(project, user, db)

    member = _get_member_or_404(db, project.id, user_id)
    if member.user_id == project.owner_id or member.role == "owner":
        raise HTTPException(status_code=400, detail="The project owner cannot be removed")

    member_name = member.user.full_name if member.user else "Member"
    db.delete(member)
    log_activity(
        db,
        actor=user,
        action="member_removed",
        summary=f"removed {member_name} from {project.name}",
        project_id=project.id,
        meta={"user_id": user_id},
    )
    db.commit()
    return Message(detail=f"{member_name} removed from {project.name}")


# ----------------------------------------------------------------------- labels
@router.get("/{project_id}/labels", response_model=list[LabelPublic])
def list_labels(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Label]:
    get_project_or_404(project_id, db, user)
    return (
        db.query(Label)
        .filter(Label.project_id == project_id)
        .order_by(Label.name.asc(), Label.id.asc())
        .all()
    )


@router.post("/{project_id}/labels", response_model=LabelPublic, status_code=201)
def create_label(
    project_id: int,
    payload: LabelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Label:
    project = get_project_or_404(project_id, db, user)
    require_edit(project, user, db)

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Label name cannot be empty")

    label = Label(project_id=project.id, name=name, color=payload.color)
    db.add(label)
    log_activity(
        db,
        actor=user,
        action="label_created",
        summary=f"added label {name} to {project.name}",
        project_id=project.id,
        meta={"name": name, "color": payload.color},
    )
    db.commit()
    db.refresh(label)
    return label


@label_router.delete("/{label_id}", response_model=Message)
def delete_label(
    label_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    label = db.query(Label).filter(Label.id == label_id).first()
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")

    project = get_project_or_404(label.project_id, db, user)
    require_edit(project, user, db)

    name = label.name
    # SQLite does not enforce foreign keys by default, so drop the links explicitly.
    db.execute(task_labels.delete().where(task_labels.c.label_id == label.id))
    db.delete(label)
    log_activity(
        db,
        actor=user,
        action="label_deleted",
        summary=f"removed label {name} from {project.name}",
        project_id=project.id,
        meta={"name": name},
    )
    db.commit()
    return Message(detail=f"Label {name} deleted")
