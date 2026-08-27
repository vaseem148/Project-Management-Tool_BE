from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

TaskStatus = Literal["backlog", "todo", "in_progress", "in_review", "done"]
TaskPriority = Literal["low", "medium", "high", "urgent"]
ProjectStatus = Literal["active", "on_hold", "completed", "archived"]
MemberRole = Literal["owner", "admin", "member", "viewer"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- users / auth
class UserPublic(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    job_title: str | None = None
    avatar_color: str | None = "violet"
    bio: str | None = ""
    created_at: datetime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=72)
    job_title: str | None = "Team Member"


class UserUpdate(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    avatar_color: str | None = None
    bio: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------------------------------------------------------------------- labels
class LabelBase(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str = "slate"


class LabelCreate(LabelBase):
    pass


class LabelPublic(ORMModel):
    id: int
    project_id: int
    name: str
    color: str


# --------------------------------------------------------------------- members
class MemberCreate(BaseModel):
    user_id: int
    role: MemberRole = "member"


class MemberUpdate(BaseModel):
    role: MemberRole


class MemberPublic(ORMModel):
    id: int
    project_id: int
    role: MemberRole
    joined_at: datetime | None = None
    user: UserPublic


# -------------------------------------------------------------------- projects
class ProjectBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = ""
    color: str = "violet"
    status: ProjectStatus = "active"
    start_date: date | None = None
    due_date: date | None = None


class ProjectCreate(ProjectBase):
    key: str | None = Field(default=None, max_length=10)
    member_ids: list[int] = []


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    due_date: date | None = None


class ProjectStats(BaseModel):
    total_tasks: int = 0
    done_tasks: int = 0
    in_progress_tasks: int = 0
    overdue_tasks: int = 0
    progress: int = 0  # 0-100
    member_count: int = 0


class ProjectPublic(ORMModel):
    id: int
    key: str
    name: str
    description: str | None = ""
    color: str
    status: ProjectStatus
    start_date: date | None = None
    due_date: date | None = None
    created_at: datetime | None = None
    owner: UserPublic | None = None
    members: list[MemberPublic] = []
    stats: ProjectStats = ProjectStats()


class ProjectSummary(ORMModel):
    id: int
    key: str
    name: str
    color: str
    status: ProjectStatus


# ----------------------------------------------------------------- subtasks
class SubtaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)


class SubtaskUpdate(BaseModel):
    title: str | None = None
    is_done: bool | None = None


class SubtaskPublic(ORMModel):
    id: int
    task_id: int
    title: str
    is_done: bool


# ----------------------------------------------------------------- comments
class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class CommentPublic(ORMModel):
    id: int
    task_id: int
    body: str
    created_at: datetime | None = None
    author: UserPublic | None = None


# -------------------------------------------------------------------- tasks
class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = ""
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    assignee_id: int | None = None
    due_date: date | None = None
    estimate_hours: float | None = None


class TaskCreate(TaskBase):
    project_id: int
    label_ids: list[int] = []


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    due_date: date | None = None
    estimate_hours: float | None = None
    label_ids: list[int] | None = None


class TaskMove(BaseModel):
    status: TaskStatus
    position: float | None = None


class TaskPublic(ORMModel):
    id: int
    project_id: int
    title: str
    description: str | None = ""
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None = None
    estimate_hours: float | None = None
    position: float = 1000.0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    assignee: UserPublic | None = None
    reporter: UserPublic | None = None
    labels: list[LabelPublic] = []
    project: ProjectSummary | None = None
    comment_count: int = 0
    subtask_count: int = 0
    subtask_done_count: int = 0


class TaskDetail(TaskPublic):
    subtasks: list[SubtaskPublic] = []
    comments: list[CommentPublic] = []


# ----------------------------------------------------------------- activity
class ActivityPublic(ORMModel):
    id: int
    action: str
    summary: str
    meta: dict[str, Any] | None = None
    created_at: datetime | None = None
    actor: UserPublic | None = None
    project: ProjectSummary | None = None
    task_id: int | None = None


# ---------------------------------------------------------------- dashboard
class CountByKey(BaseModel):
    key: str
    label: str
    count: int


class TrendPoint(BaseModel):
    date: str
    created: int
    completed: int


class WorkloadEntry(BaseModel):
    user: UserPublic
    open_tasks: int
    done_tasks: int


class DashboardSummary(BaseModel):
    total_projects: int
    active_projects: int
    total_tasks: int
    my_open_tasks: int
    completed_tasks: int
    overdue_tasks: int
    due_soon_tasks: int
    completion_rate: int
    tasks_by_status: list[CountByKey]
    tasks_by_priority: list[CountByKey]
    trend: list[TrendPoint]
    workload: list[WorkloadEntry]
    upcoming: list[TaskPublic]
    recent_activity: list[ActivityPublic]
    projects: list[ProjectPublic]


class Message(BaseModel):
    detail: str
