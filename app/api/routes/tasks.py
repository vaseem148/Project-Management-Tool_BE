"""Tasks, subtasks and comments."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import (
    get_current_user,
    get_project_or_404,
    require_admin,
    require_edit,
    user_can_view,
)
from app.core.database import get_db
from app.models import Comment, Label, Project, ProjectMember, Subtask, Task, User
from app.schemas import (
    CommentCreate,
    CommentPublic,
    Message,
    SubtaskCreate,
    SubtaskPublic,
    SubtaskUpdate,
    TaskCreate,
    TaskDetail,
    TaskMove,
    TaskPublic,
    TaskUpdate,
)
from app.services.serializers import (
    log_activity,
    next_position,
    serialize_task,
    serialize_task_detail,
    serialize_tasks,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
subtask_router = APIRouter(tags=["tasks"])
comment_router = APIRouter(tags=["tasks"])

STATUS_LABELS: dict[str, str] = {
    "backlog": "Backlog",
    "todo": "To Do",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
}
PRIORITY_LABELS: dict[str, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "urgent": "Urgent",
}
SORT_FIELDS = {"position", "due_date", "priority", "created_at"}
DUE_FILTERS = {"overdue", "today", "week"}

_PRIORITY_RANK = case(
    {"urgent": 0, "high": 1, "medium": 2, "low": 3},
    value=Task.priority,
    else_=4,
)
_DUE_DATE_NULLS_LAST = case((Task.due_date.is_(None), 1), else_=0)


# --------------------------------------------------------------------- helpers
def _short(text: str, limit: int = 90) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _actor_name(user: User) -> str:
    return user.full_name or user.email


def _visible_project_ids(user: User):
    """Sub-select of the projects the user belongs to (inlined, never executed alone)."""
    return select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)


def _task_options():
    return (
        joinedload(Task.assignee),
        joinedload(Task.reporter),
        joinedload(Task.project),
        selectinload(Task.labels),
    )


def _get_task(db: Session, task_id: int, user: User) -> Task:
    task = db.query(Task).options(*_task_options()).filter(Task.id == task_id).first()
    if task is None or task.project is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not user_can_view(task.project, user, db):
        raise HTTPException(status_code=403, detail="You do not have access to this task")
    return task


def _editable_task(db: Session, task_id: int, user: User) -> Task:
    task = _get_task(db, task_id, user)
    require_edit(task.project, user, db)
    return task


def _labels_for_project(db: Session, project_id: int, label_ids: list[int]) -> list[Label]:
    ids = {int(i) for i in label_ids}
    if not ids:
        return []
    return db.query(Label).filter(Label.project_id == project_id, Label.id.in_(ids)).all()


def _check_assignee(db: Session, assignee_id: int | None) -> None:
    if assignee_id is None:
        return
    if db.query(User.id).filter(User.id == assignee_id).first() is None:
        raise HTTPException(status_code=404, detail="Assignee not found")


# ----------------------------------------------------------------------- tasks
@router.get("", response_model=list[TaskPublic])
def list_tasks(
    project_id: int | None = Query(default=None),
    status: list[str] | None = Query(default=None, description="Repeatable status filter"),
    priority: list[str] | None = Query(default=None, description="Repeatable priority filter"),
    assignee_id: int | None = Query(default=None),
    label_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    due: str | None = Query(default=None, description="overdue | today | week"),
    mine: bool = Query(default=False),
    sort: str = Query(default="position", description="position | due_date | priority | created_at"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskPublic]:
    query = (
        db.query(Task)
        .join(Project, Task.project_id == Project.id)
        .options(*_task_options())
        .filter(
            or_(
                Project.owner_id == current_user.id,
                Task.project_id.in_(_visible_project_ids(current_user)),
            )
        )
    )

    if project_id is not None:
        project = get_project_or_404(project_id, db, current_user)
        query = query.filter(Task.project_id == project.id)

    statuses = [s for s in (status or []) if s in STATUS_LABELS]
    if statuses:
        query = query.filter(Task.status.in_(statuses))

    priorities = [p for p in (priority or []) if p in PRIORITY_LABELS]
    if priorities:
        query = query.filter(Task.priority.in_(priorities))

    if assignee_id is not None:
        query = query.filter(Task.assignee_id == assignee_id)
    if mine:
        query = query.filter(Task.assignee_id == current_user.id)
    if label_id is not None:
        query = query.filter(Task.labels.any(Label.id == label_id))

    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(Task.title.ilike(needle), Task.description.ilike(needle)))

    if due in DUE_FILTERS:
        today = date.today()
        if due == "overdue":
            query = query.filter(
                Task.due_date.isnot(None),
                Task.due_date < today,
                Task.status != "done",
            )
        elif due == "today":
            query = query.filter(Task.due_date == today)
        else:  # week -> due within the next 7 days
            query = query.filter(
                Task.due_date.isnot(None),
                Task.due_date >= today,
                Task.due_date <= today + timedelta(days=7),
            )

    sort_key = sort if sort in SORT_FIELDS else "position"
    if sort_key == "due_date":
        query = query.order_by(
            _DUE_DATE_NULLS_LAST.asc(), Task.due_date.asc(), Task.position.asc()
        )
    elif sort_key == "priority":
        query = query.order_by(_PRIORITY_RANK.asc(), Task.position.asc(), Task.id.asc())
    elif sort_key == "created_at":
        query = query.order_by(Task.created_at.desc(), Task.id.desc())
    else:
        query = query.order_by(Task.position.asc(), Task.id.asc())

    tasks = query.limit(limit).all()
    return serialize_tasks(db, tasks)


@router.post("", response_model=TaskPublic, status_code=201)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    project = get_project_or_404(payload.project_id, db, current_user)
    require_edit(project, current_user, db)
    _check_assignee(db, payload.assignee_id)

    task = Task(
        project_id=project.id,
        title=payload.title.strip(),
        description=payload.description or "",
        status=payload.status,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        reporter_id=current_user.id,
        due_date=payload.due_date,
        estimate_hours=payload.estimate_hours,
        position=next_position(db, project.id, payload.status),
        completed_at=datetime.now(timezone.utc) if payload.status == "done" else None,
    )
    task.labels = _labels_for_project(db, project.id, payload.label_ids)
    db.add(task)
    db.flush()

    log_activity(
        db,
        actor=current_user,
        action="task_created",
        summary=f'{_actor_name(current_user)} created "{_short(task.title)}"',
        project_id=project.id,
        task_id=task.id,
        meta={"status": task.status, "priority": task.priority},
    )
    db.commit()
    db.refresh(task)
    return serialize_task(db, task)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDetail:
    task = _get_task(db, task_id, current_user)
    return serialize_task_detail(db, task)


@router.patch("/{task_id}", response_model=TaskPublic)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    task = _editable_task(db, task_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    label_ids = data.pop("label_ids", None)

    previous_status: str = task.status
    previous_assignee_id: int | None = task.assignee_id

    if "assignee_id" in data:
        _check_assignee(db, data["assignee_id"])

    for field, value in data.items():
        if value is None and field in {"title", "status", "priority"}:
            continue  # never blank out required columns
        if field == "title":
            value = value.strip()
        elif field == "description" and value is None:
            value = ""
        setattr(task, field, value)

    if task.status == "done" and previous_status != "done":
        task.completed_at = datetime.now(timezone.utc)
    elif task.status != "done" and previous_status == "done":
        task.completed_at = None

    if label_ids is not None:
        task.labels = _labels_for_project(db, task.project_id, label_ids)

    changes: list[str] = []
    if task.status != previous_status:
        changes.append(
            f"{STATUS_LABELS.get(previous_status, previous_status)} -> "
            f"{STATUS_LABELS.get(task.status, task.status)}"
        )
    if task.assignee_id != previous_assignee_id:
        if task.assignee_id is None:
            changes.append("unassigned")
        else:
            assignee = db.query(User).filter(User.id == task.assignee_id).first()
            changes.append(f"assigned to {_actor_name(assignee) if assignee else 'someone'}")

    summary = f'{_actor_name(current_user)} updated "{_short(task.title)}"'
    if changes:
        summary = f"{summary} ({', '.join(changes)})"

    fields = set(data.keys())
    if label_ids is not None:
        fields.add("labels")

    log_activity(
        db,
        actor=current_user,
        action="task_updated",
        summary=_short(summary, 380),
        project_id=task.project_id,
        task_id=task.id,
        meta={
            "fields": sorted(fields),
            "from_status": previous_status,
            "to_status": task.status,
        },
    )
    db.commit()
    db.refresh(task)
    return serialize_task(db, task)


@router.delete("/{task_id}", response_model=Message)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    task = _editable_task(db, task_id, current_user)
    title = task.title
    project_id = task.project_id

    db.delete(task)
    db.flush()
    log_activity(
        db,
        actor=current_user,
        action="task_deleted",
        summary=f'{_actor_name(current_user)} deleted "{_short(title)}"',
        project_id=project_id,
        meta={"title": title},
    )
    db.commit()
    return Message(detail="Task deleted")


@router.post("/{task_id}/move", response_model=TaskPublic)
def move_task(
    task_id: int,
    payload: TaskMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    task = _editable_task(db, task_id, current_user)
    previous_status: str = task.status

    task.status = payload.status
    task.position = (
        payload.position
        if payload.position is not None
        else next_position(db, task.project_id, payload.status)
    )

    if task.status == "done" and previous_status != "done":
        task.completed_at = datetime.now(timezone.utc)
    elif task.status != "done" and previous_status == "done":
        task.completed_at = None

    log_activity(
        db,
        actor=current_user,
        action="task_moved",
        summary=(
            f'{_actor_name(current_user)} moved "{_short(task.title)}" to '
            f"{STATUS_LABELS.get(task.status, task.status)}"
        ),
        project_id=task.project_id,
        task_id=task.id,
        meta={"from": previous_status, "to": task.status, "position": task.position},
    )
    db.commit()
    db.refresh(task)
    return serialize_task(db, task)


# -------------------------------------------------------------------- subtasks
@router.post("/{task_id}/subtasks", response_model=SubtaskPublic, status_code=201)
def create_subtask(
    task_id: int,
    payload: SubtaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubtaskPublic:
    task = _editable_task(db, task_id, current_user)
    subtask = Subtask(task_id=task.id, title=payload.title.strip(), is_done=False)
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return SubtaskPublic.model_validate(subtask)


def _get_subtask(db: Session, subtask_id: int, user: User) -> Subtask:
    subtask = db.query(Subtask).filter(Subtask.id == subtask_id).first()
    if subtask is None:
        raise HTTPException(status_code=404, detail="Subtask not found")
    _editable_task(db, subtask.task_id, user)
    return subtask


@subtask_router.patch("/subtasks/{subtask_id}", response_model=SubtaskPublic)
def update_subtask(
    subtask_id: int,
    payload: SubtaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubtaskPublic:
    subtask = _get_subtask(db, subtask_id, current_user)
    if payload.title is not None:
        subtask.title = payload.title.strip()
    if payload.is_done is not None:
        subtask.is_done = payload.is_done
    db.commit()
    db.refresh(subtask)
    return SubtaskPublic.model_validate(subtask)


@subtask_router.delete("/subtasks/{subtask_id}", response_model=Message)
def delete_subtask(
    subtask_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    subtask = _get_subtask(db, subtask_id, current_user)
    db.delete(subtask)
    db.commit()
    return Message(detail="Subtask deleted")


# -------------------------------------------------------------------- comments
@router.get("/{task_id}/comments", response_model=list[CommentPublic])
def list_comments(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommentPublic]:
    task = _get_task(db, task_id, current_user)
    comments = (
        db.query(Comment)
        .options(joinedload(Comment.author))
        .filter(Comment.task_id == task.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .all()
    )
    return [CommentPublic.model_validate(comment) for comment in comments]


@router.post("/{task_id}/comments", response_model=CommentPublic, status_code=201)
def create_comment(
    task_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommentPublic:
    task = _get_task(db, task_id, current_user)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")

    comment = Comment(task_id=task.id, author_id=current_user.id, body=body)
    db.add(comment)
    db.flush()
    log_activity(
        db,
        actor=current_user,
        action="comment_added",
        summary=f'{_actor_name(current_user)} commented on "{_short(task.title)}"',
        project_id=task.project_id,
        task_id=task.id,
        meta={"excerpt": _short(body, 140)},
    )
    db.commit()
    db.refresh(comment)
    return CommentPublic.model_validate(comment)


@comment_router.delete("/comments/{comment_id}", response_model=Message)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    task = _get_task(db, comment.task_id, current_user)
    if comment.author_id != current_user.id:
        require_admin(task.project, current_user, db)
    db.delete(comment)
    db.commit()
    return Message(detail="Comment deleted")
