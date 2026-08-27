"""Dashboard aggregates and the global activity feed."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_project_or_404
from app.core.database import get_db
from app.models import Activity, Project, ProjectMember, Task, User
from app.schemas import (
    ActivityPublic,
    CountByKey,
    DashboardSummary,
    TrendPoint,
    UserPublic,
    WorkloadEntry,
)
from app.services.serializers import serialize_activity, serialize_project, serialize_tasks

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
activity_router = APIRouter(prefix="/activity", tags=["dashboard"])

TREND_DAYS = 14
DUE_SOON_DAYS = 7
WORKLOAD_LIMIT = 6
UPCOMING_LIMIT = 6
RECENT_ACTIVITY_LIMIT = 8

STATUS_LABELS: list[tuple[str, str]] = [
    ("backlog", "Backlog"),
    ("todo", "To Do"),
    ("in_progress", "In Progress"),
    ("in_review", "In Review"),
    ("done", "Done"),
]

PRIORITY_LABELS: list[tuple[str, str]] = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("urgent", "Urgent"),
]

# Active projects first on the dashboard, archived last.
PROJECT_STATUS_ORDER = case(
    (Project.status == "active", 0),
    (Project.status == "on_hold", 1),
    (Project.status == "completed", 2),
    else_=3,
)


def visible_project_ids(db: Session, user: User) -> list[int]:
    """Ids of every project the user owns or is a member of."""
    owned = {pid for (pid,) in db.query(Project.id).filter(Project.owner_id == user.id).all()}
    joined = {
        pid
        for (pid,) in db.query(ProjectMember.project_id)
        .filter(ProjectMember.user_id == user.id)
        .all()
    }
    return sorted(owned | joined)


def _count(db: Session, *filters) -> int:
    return int(db.query(func.count(Task.id)).filter(*filters).scalar() or 0)


def _bucket_counts(counts: dict[str, int], labels: list[tuple[str, str]]) -> list[CountByKey]:
    return [CountByKey(key=key, label=label, count=counts.get(key, 0)) for key, label in labels]


def _trend_points(db: Session, project_ids: list[int]) -> list[TrendPoint]:
    """Created vs. completed task counts for each of the last TREND_DAYS days."""
    today = date.today()
    days = [today - timedelta(days=offset) for offset in range(TREND_DAYS - 1, -1, -1)]
    created: dict[str, int] = {}
    completed: dict[str, int] = {}

    if project_ids:
        window_start = datetime.combine(days[0], time.min)
        created_rows = (
            db.query(func.date(Task.created_at), func.count(Task.id))
            .filter(Task.project_id.in_(project_ids), Task.created_at >= window_start)
            .group_by(func.date(Task.created_at))
            .all()
        )
        created = {str(day): int(count) for day, count in created_rows if day}

        completed_rows = (
            db.query(func.date(Task.completed_at), func.count(Task.id))
            .filter(
                Task.project_id.in_(project_ids),
                Task.completed_at.isnot(None),
                Task.completed_at >= window_start,
            )
            .group_by(func.date(Task.completed_at))
            .all()
        )
        completed = {str(day): int(count) for day, count in completed_rows if day}

    return [
        TrendPoint(
            date=day.isoformat(),
            created=created.get(day.isoformat(), 0),
            completed=completed.get(day.isoformat(), 0),
        )
        for day in days
    ]


def _workload(db: Session, project_ids: list[int]) -> list[WorkloadEntry]:
    """Open / done task counts per assignee, busiest first."""
    if not project_ids:
        return []
    open_expr = func.sum(case((Task.status != "done", 1), else_=0))
    done_expr = func.sum(case((Task.status == "done", 1), else_=0))
    rows = (
        db.query(Task.assignee_id, open_expr.label("open_tasks"), done_expr.label("done_tasks"))
        .filter(Task.project_id.in_(project_ids), Task.assignee_id.isnot(None))
        .group_by(Task.assignee_id)
        .order_by(open_expr.desc(), done_expr.desc(), Task.assignee_id.asc())
        .limit(WORKLOAD_LIMIT)
        .all()
    )
    if not rows:
        return []

    users = {
        user.id: user
        for user in db.query(User).filter(User.id.in_([row[0] for row in rows])).all()
    }
    entries: list[WorkloadEntry] = []
    for user_id, open_tasks, done_tasks in rows:
        member = users.get(user_id)
        if member is None:
            continue
        entries.append(
            WorkloadEntry(
                user=UserPublic.model_validate(member),
                open_tasks=int(open_tasks or 0),
                done_tasks=int(done_tasks or 0),
            )
        )
    return entries


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DashboardSummary:
    project_ids = visible_project_ids(db, user)
    today = date.today()

    if not project_ids:
        return DashboardSummary(
            total_projects=0,
            active_projects=0,
            total_tasks=0,
            my_open_tasks=0,
            completed_tasks=0,
            overdue_tasks=0,
            due_soon_tasks=0,
            completion_rate=0,
            tasks_by_status=_bucket_counts({}, STATUS_LABELS),
            tasks_by_priority=_bucket_counts({}, PRIORITY_LABELS),
            trend=_trend_points(db, []),
            workload=[],
            upcoming=[],
            recent_activity=[],
            projects=[],
        )

    projects = (
        db.query(Project)
        .filter(Project.id.in_(project_ids))
        .order_by(PROJECT_STATUS_ORDER.asc(), Project.updated_at.desc(), Project.id.asc())
        .all()
    )
    active_projects = sum(1 for project in projects if project.status == "active")

    status_counts = {
        str(status): int(count)
        for status, count in db.query(Task.status, func.count(Task.id))
        .filter(Task.project_id.in_(project_ids))
        .group_by(Task.status)
        .all()
    }
    priority_counts = {
        str(priority): int(count)
        for priority, count in db.query(Task.priority, func.count(Task.id))
        .filter(Task.project_id.in_(project_ids))
        .group_by(Task.priority)
        .all()
    }

    total_tasks = sum(status_counts.values())
    completed_tasks = status_counts.get("done", 0)

    my_open_tasks = _count(
        db,
        Task.project_id.in_(project_ids),
        Task.assignee_id == user.id,
        Task.status != "done",
    )
    overdue_tasks = _count(
        db,
        Task.project_id.in_(project_ids),
        Task.status != "done",
        Task.due_date.isnot(None),
        Task.due_date < today,
    )
    due_soon_tasks = _count(
        db,
        Task.project_id.in_(project_ids),
        Task.status != "done",
        Task.due_date.isnot(None),
        Task.due_date >= today,
        Task.due_date <= today + timedelta(days=DUE_SOON_DAYS),
    )

    upcoming = (
        db.query(Task)
        .filter(
            Task.project_id.in_(project_ids),
            Task.status != "done",
            Task.due_date.isnot(None),
        )
        .order_by(Task.due_date.asc(), Task.id.asc())
        .limit(UPCOMING_LIMIT)
        .all()
    )

    recent_activity = (
        db.query(Activity)
        .filter(Activity.project_id.in_(project_ids))
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
        .all()
    )

    return DashboardSummary(
        total_projects=len(projects),
        active_projects=active_projects,
        total_tasks=total_tasks,
        my_open_tasks=my_open_tasks,
        completed_tasks=completed_tasks,
        overdue_tasks=overdue_tasks,
        due_soon_tasks=due_soon_tasks,
        completion_rate=int(round(completed_tasks / total_tasks * 100)) if total_tasks else 0,
        tasks_by_status=_bucket_counts(status_counts, STATUS_LABELS),
        tasks_by_priority=_bucket_counts(priority_counts, PRIORITY_LABELS),
        trend=_trend_points(db, project_ids),
        workload=_workload(db, project_ids),
        upcoming=serialize_tasks(db, upcoming),
        recent_activity=[serialize_activity(entry) for entry in recent_activity],
        projects=[serialize_project(db, project) for project in projects],
    )


@activity_router.get("", response_model=list[ActivityPublic])
def list_activity(
    project_id: int | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ActivityPublic]:
    if project_id is not None:
        project = get_project_or_404(project_id, db, user)
        project_ids = [project.id]
    else:
        project_ids = visible_project_ids(db, user)
    if not project_ids:
        return []

    entries = (
        db.query(Activity)
        .filter(Activity.project_id.in_(project_ids))
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(limit)
        .all()
    )
    return [serialize_activity(entry) for entry in entries]
