"""Helpers that turn ORM rows into the shapes declared in app.schemas."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Activity, Comment, Project, ProjectMember, Subtask, Task, User
from app.schemas import (
    ActivityPublic,
    ProjectPublic,
    ProjectStats,
    TaskDetail,
    TaskPublic,
)


def compute_project_stats(db: Session, project: Project) -> ProjectStats:
    rows = (
        db.query(Task.status, func.count(Task.id))
        .filter(Task.project_id == project.id)
        .group_by(Task.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    total = sum(counts.values())
    done = counts.get("done", 0)
    overdue = (
        db.query(func.count(Task.id))
        .filter(
            Task.project_id == project.id,
            Task.status != "done",
            Task.due_date.isnot(None),
            Task.due_date < date.today(),
        )
        .scalar()
        or 0
    )
    members = (
        db.query(func.count(ProjectMember.id))
        .filter(ProjectMember.project_id == project.id)
        .scalar()
        or 0
    )
    return ProjectStats(
        total_tasks=total,
        done_tasks=done,
        in_progress_tasks=counts.get("in_progress", 0),
        overdue_tasks=overdue,
        progress=int(round(done / total * 100)) if total else 0,
        member_count=members,
    )


def serialize_project(db: Session, project: Project) -> ProjectPublic:
    payload = ProjectPublic.model_validate(project)
    payload.stats = compute_project_stats(db, project)
    return payload


def _counts_for_task(db: Session, task: Task) -> tuple[int, int, int]:
    comment_count = db.query(func.count(Comment.id)).filter(Comment.task_id == task.id).scalar() or 0
    subtask_total = db.query(func.count(Subtask.id)).filter(Subtask.task_id == task.id).scalar() or 0
    subtask_done = (
        db.query(func.count(Subtask.id))
        .filter(Subtask.task_id == task.id, Subtask.is_done.is_(True))
        .scalar()
        or 0
    )
    return comment_count, subtask_total, subtask_done


def serialize_task(db: Session, task: Task) -> TaskPublic:
    payload = TaskPublic.model_validate(task)
    comments, subtasks, subtasks_done = _counts_for_task(db, task)
    payload.comment_count = comments
    payload.subtask_count = subtasks
    payload.subtask_done_count = subtasks_done
    return payload


def serialize_tasks(db: Session, tasks: list[Task]) -> list[TaskPublic]:
    return [serialize_task(db, task) for task in tasks]


def serialize_task_detail(db: Session, task: Task) -> TaskDetail:
    payload = TaskDetail.model_validate(task)
    comments, subtasks, subtasks_done = _counts_for_task(db, task)
    payload.comment_count = comments
    payload.subtask_count = subtasks
    payload.subtask_done_count = subtasks_done
    payload.comments = sorted(payload.comments, key=lambda c: c.created_at or datetime.min)
    return payload


def serialize_activity(activity: Activity) -> ActivityPublic:
    return ActivityPublic.model_validate(activity)


def log_activity(
    db: Session,
    *,
    actor: User | None,
    action: str,
    summary: str,
    project_id: int | None = None,
    task_id: int | None = None,
    meta: dict | None = None,
) -> Activity:
    entry = Activity(
        actor_id=actor.id if actor else None,
        action=action,
        summary=summary,
        project_id=project_id,
        task_id=task_id,
        meta=meta or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    return entry


def next_position(db: Session, project_id: int, status: str) -> float:
    highest = (
        db.query(func.max(Task.position))
        .filter(Task.project_id == project_id, Task.status == status)
        .scalar()
    )
    return (highest or 0.0) + 1000.0
