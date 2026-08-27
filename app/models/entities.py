from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


task_labels = Table(
    "task_labels",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", Integer, ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    job_title = Column(String(120), default="Team Member")
    avatar_color = Column(String(20), default="violet")
    bio = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")
    owned_projects = relationship("Project", back_populates="owner", foreign_keys="Project.owner_id")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(10), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, default="")
    color = Column(String(20), default="violet")
    status = Column(String(20), default="active")  # active | on_hold | completed | archived
    start_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User", back_populates="owned_projects", foreign_keys=[owner_id])
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    labels = relationship("Label", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_user"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="member")  # owner | admin | member | viewer
    joined_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="memberships")


class Label(Base):
    __tablename__ = "labels"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(60), nullable=False)
    color = Column(String(20), default="slate")

    project = relationship("Project", back_populates="labels")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(240), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="todo", index=True)  # backlog|todo|in_progress|in_review|done
    priority = Column(String(20), default="medium", index=True)  # low|medium|high|urgent
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reporter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    estimate_hours = Column(Float, nullable=True)
    position = Column(Float, default=1000.0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id])
    reporter = relationship("User", foreign_keys=[reporter_id])
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    labels = relationship("Label", secondary=task_labels, lazy="selectin")
    subtasks = relationship("Subtask", back_populates="task", cascade="all, delete-orphan")


class Subtask(Base):
    __tablename__ = "subtasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(240), nullable=False)
    is_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    task = relationship("Task", back_populates="subtasks")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    task = relationship("Task", back_populates="comments")
    author = relationship("User")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(60), nullable=False)
    summary = Column(String(400), default="")
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow, index=True)

    actor = relationship("User")
    project = relationship("Project")
