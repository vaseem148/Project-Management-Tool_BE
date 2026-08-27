"""Deterministic demo data.

Running the seeder twice is a no-op: it bails out as soon as a single ``User``
row exists. Everything below is derived from fixed tables plus index
arithmetic, so a fresh database always looks exactly the same (only the dates
move, because they are anchored to "now").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Activity, Comment, Label, Project, ProjectMember, Subtask, Task, User

DEMO_PASSWORD = "demo1234"
DEMO_EMAIL = "demo@pmt.app"

# email, full name, job title, avatar colour, bio
USERS: list[tuple[str, str, str, str, str]] = [
    (
        DEMO_EMAIL,
        "Aarav Sharma",
        "Product Lead",
        "violet",
        "Keeps the roadmap honest and the standups short.",
    ),
    (
        "priya@pmt.app",
        "Priya Menon",
        "Engineering Manager",
        "cyan",
        "Unblocks people, then gets out of the way.",
    ),
    (
        "rahul@pmt.app",
        "Rahul Verma",
        "Senior Frontend Engineer",
        "indigo",
        "React, animations and an unhealthy love of keyboard shortcuts.",
    ),
    (
        "sara@pmt.app",
        "Sara Khan",
        "Backend Engineer",
        "emerald",
        "APIs, queues and query plans.",
    ),
    (
        "diego@pmt.app",
        "Diego Alvarez",
        "Product Designer",
        "amber",
        "Design systems, motion and pixel arguments worth having.",
    ),
    (
        "mei@pmt.app",
        "Mei Lin",
        "QA Engineer",
        "rose",
        "Finds the edge case you swore could never happen.",
    ),
]

# key, name, description, colour, status, start offset, due offset, owner idx, members
PROJECTS: list[tuple[str, str, str, str, str, int, int, int, list[tuple[int, str]]]] = [
    (
        "NWA",
        "Nexus Web App",
        "The core web client: dashboard, kanban board, task detail and everything around it.",
        "violet",
        "active",
        -34,
        24,
        0,
        [(0, "owner"), (1, "admin"), (2, "member"), (3, "member"), (4, "member"), (5, "member")],
    ),
    (
        "MA2",
        "Mobile App 2.0",
        "A ground-up rewrite of the iOS and Android clients with offline-first sync.",
        "cyan",
        "active",
        -18,
        45,
        1,
        [(1, "owner"), (0, "admin"), (2, "member"), (3, "member"), (5, "member")],
    ),
    (
        "MW",
        "Marketing Website",
        "Public site refresh: new pricing page, case studies and a much faster hero.",
        "amber",
        "on_hold",
        -47,
        12,
        0,
        [(0, "owner"), (4, "admin"), (1, "member"), (5, "member")],
    ),
    (
        "DS",
        "Design System",
        "Shared tokens, primitives and documentation used by every Nexus surface.",
        "emerald",
        "completed",
        -63,
        -3,
        2,
        [(2, "owner"), (0, "admin"), (3, "member"), (4, "member")],
    ),
]

# Same four defaults the projects router creates for new projects.
LABELS: list[tuple[str, str]] = [
    ("Bug", "rose"),
    ("Feature", "violet"),
    ("Design", "cyan"),
    ("Docs", "amber"),
]

# project idx, title, description, status, priority, assignee idx, due offset, estimate hours
TASKS: list[tuple[int, str, str, str, str, int, int | None, float]] = [
    # ------------------------------------------------------------ Nexus Web App
    (0, "Design the dashboard shell layout", "Sidebar, top bar and the responsive grid the widgets sit on.", "done", "high", 4, -12, 8.0),
    (0, "Implement the JWT auth flow", "Register, login, token refresh on the client and the bearer dependency on the API.", "done", "urgent", 3, -10, 10.0),
    (0, "Kanban board drag and drop", "Five columns, optimistic reordering and a position-based move endpoint.", "in_progress", "urgent", 2, 2, 16.0),
    (0, "Task detail drawer with comments", "Slide-over with description editing, subtasks, labels and the comment thread.", "in_progress", "high", 2, 4, 12.0),
    (0, "Project members and roles API", "Owner / admin / member / viewer with the permission checks in deps.py.", "done", "medium", 0, -6, 6.0),
    (0, "Global command palette", "Cmd+K to jump to a project, a task or an action without touching the mouse.", "todo", "medium", 0, 9, 8.0),
    (0, "Dark mode polish pass", "Fix the low-contrast chips and the washed out borders on the board.", "in_review", "low", 4, 1, 4.0),
    (0, "Activity feed pagination", "The feed loads all rows today; page it and add a project filter.", "todo", "low", 3, 11, 5.0),
    (0, "Fix the overdue badge timezone bug", "Tasks due today show as overdue for anyone west of UTC.", "in_progress", "urgent", 5, -1, 3.0),
    (0, "End-to-end tests for the board", "Cover drag between columns, filtering and the create-task modal.", "todo", "high", 5, 6, 10.0),
    (0, "Optimise the dashboard summary query", "Replace the per-project loops with grouped aggregates.", "backlog", "medium", 0, None, 6.0),
    (0, "Realtime presence indicators", "Show who else is looking at a project, over a websocket channel.", "backlog", "low", 1, None, 20.0),
    (0, "Bulk task actions", "Multi-select on the list view to reassign, relabel or close in one go.", "backlog", "medium", 1, None, 12.0),
    (0, "Onboarding empty states", "Every list needs an illustrated empty state with a real call to action.", "in_review", "medium", 0, 3, 5.0),
    (0, "Accessibility audit for modals", "Focus trap, escape to close, aria labels on every icon-only button.", "todo", "high", 5, 5, 6.0),
    (0, "Set up the CI pipeline", "Lint, typecheck and test on every pull request.", "done", "high", 1, -15, 4.0),
    # ---------------------------------------------------------- Mobile App 2.0
    (1, "Offline-first sync engine", "Local queue with conflict resolution so the app works on the metro.", "in_progress", "urgent", 3, 8, 24.0),
    (1, "Push notification opt-in flow", "Ask at the right moment, not on first launch.", "todo", "high", 2, 5, 8.0),
    (1, "Biometric login", "Face ID and fingerprint unlock backed by the keychain.", "done", "high", 3, -4, 10.0),
    (1, "Redesign the task card for small screens", "Two lines of title, avatar, due chip. Nothing else fits.", "in_review", "medium", 2, 2, 6.0),
    (1, "Crash on Android 13 cold start", "Null database handle when the app is restored from a killed state.", "in_progress", "urgent", 5, -2, 5.0),
    (1, "Bottom sheet navigation", "Replace the tab bar with a gesture-driven sheet.", "todo", "medium", 2, 12, 9.0),
    (1, "Ship the 2.0 beta to TestFlight", "Build, changelog and the internal tester group.", "todo", "high", 1, 6, 3.0),
    (1, "Reduce the bundle below 8 MB", "Drop the unused icon set and split the onboarding assets.", "backlog", "low", 2, None, 8.0),
    (1, "Localise strings for hi-IN", "Extract the hardcoded copy first, then hand it to the translators.", "backlog", "medium", 0, None, 12.0),
    (1, "Analytics event taxonomy", "One naming scheme for every screen and action before we add more events.", "done", "medium", 0, -7, 6.0),
    (1, "Fix the pull-to-refresh flicker", "The list rebuilds twice because the query key changes mid-refresh.", "done", "low", 5, -9, 2.0),
    (1, "Deep links for task URLs", "Opening a nexus:// task link should land on the detail screen.", "in_review", "high", 3, 1, 7.0),
    # ------------------------------------------------------- Marketing Website
    (2, "New pricing page copy", "Three tiers, an honest comparison table and no dark patterns.", "in_progress", "high", 0, 3, 6.0),
    (2, "Hero animation with Framer", "Subtle parallax on the product shot, disabled under prefers-reduced-motion.", "in_review", "medium", 4, 1, 8.0),
    (2, "SEO metadata and sitemap", "Open Graph tags, canonical URLs and a generated sitemap.xml.", "todo", "medium", 1, 7, 4.0),
    (2, "Customer logo wall", "Twelve logos, greyscale until hover, and permission from each of them.", "done", "low", 4, -5, 3.0),
    (2, "Blog CMS integration", "Pick a headless CMS and wire up the post templates.", "backlog", "medium", 1, None, 16.0),
    (2, "Lighthouse score above 95", "Mostly images and the font loading strategy.", "todo", "high", 1, 4, 6.0),
    (2, "Cookie consent banner", "Legal wants this live before the campaign starts.", "todo", "urgent", 5, -3, 4.0),
    (2, "Case study: Northwind", "Interview done, needs writing up and design treatment.", "backlog", "low", 0, None, 10.0),
    (2, "Fix the broken footer links", "Four of them still point at the old docs domain.", "done", "low", 5, -8, 1.0),
    (2, "A/B test the signup CTA", "Two variants, one week, ship whichever wins.", "in_progress", "medium", 0, 6, 5.0),
    # ----------------------------------------------------------- Design System
    (3, "Token pipeline from Figma to CSS variables", "One source of truth for colour, spacing and radius.", "done", "high", 4, -11, 12.0),
    (3, "Button and IconButton primitives", "Five variants, three sizes, loading and disabled states.", "done", "medium", 2, -9, 8.0),
    (3, "Modal and Drawer with focus trap", "Escape to close, restore focus to the trigger, no body scroll.", "done", "high", 2, -6, 10.0),
    (3, "Avatar, Badge and Tag components", "The small pieces every list in the app repeats.", "done", "low", 4, -13, 6.0),
    (3, "Document usage in Storybook", "A page per component with do and do-not examples.", "in_review", "medium", 4, 2, 8.0),
    (3, "Dark theme contrast fixes", "Six tokens fail AA on the elevated surface.", "done", "medium", 4, -4, 5.0),
    (3, "Form controls: Select and Combobox", "Keyboard navigation is the whole job here.", "in_progress", "high", 2, 9, 14.0),
    (3, "Deprecate the legacy Card variants", "Codemod the call sites, then delete the old file.", "todo", "low", 3, 14, 4.0),
]

SUBTASK_POOL: list[str] = [
    "Write the technical spec",
    "Agree the API shape with the backend",
    "Break the work into tickets",
    "Build the happy path",
    "Handle the error and empty states",
    "Add loading skeletons",
    "Cover it with tests",
    "Review with design",
    "Update the documentation",
    "Ship behind a feature flag",
    "Measure the impact",
    "Delete the dead code",
]

SUBTASK_COUNTS: list[int] = [3, 0, 4, 2, 0, 3, 2, 5, 0, 2, 3, 4]

COMMENT_POOL: list[str] = [
    "Picked this up, should have a draft PR by tomorrow.",
    "Left a couple of notes on the Figma file, nothing blocking.",
    "Careful with the timezone handling here, it bit us last sprint.",
    "Bumped the estimate. The API change is bigger than it looked.",
    "Reproduced on a clean install, so it is not a cache issue.",
    "This unblocks two other tickets, worth pulling forward.",
    "Design approved. Only the empty state copy is still open.",
    "Merged to main and deployed to staging, please have a look.",
    "Can we split the docs part into its own task?",
    "Tested on a real device, the jank is gone.",
]

COMMENT_COUNTS: list[int] = [2, 0, 3, 1, 0, 2, 1, 0, 3, 1]

# Days-ago each completed task was finished, in seed order. Deliberately lumpy so
# the 14-day trend chart looks like real work rather than a flat line.
COMPLETION_OFFSETS: list[int] = [1, 2, 2, 3, 5, 5, 6, 4, 8, 9, 9, 11, 12, 13, 7, 10]

# action, task index (or None), actor index, summary template
ACTIVITY_SPECS: list[tuple[str, int | None, int, str]] = [
    ("task_moved", 2, 2, "moved {title} to In Progress"),
    ("comment_added", 3, 4, "commented on {title}"),
    ("task_updated", 8, 5, "raised the priority of {title} to Urgent"),
    ("task_created", 5, 0, "created {title}"),
    ("task_moved", 6, 4, "moved {title} to In Review"),
    ("task_updated", 16, 1, "assigned {title} to Sara Khan"),
    ("comment_added", 20, 5, "commented on {title}"),
    ("task_moved", 27, 3, "moved {title} to In Review"),
    ("task_created", 30, 0, "created {title}"),
    ("task_updated", 34, 1, "set a due date on {title}"),
    ("comment_added", 39, 5, "commented on {title}"),
    ("task_moved", 44, 4, "moved {title} to In Review"),
    ("task_updated", 45, 2, "added the Docs label to {title}"),
    ("member_added", None, 0, "added Mei Lin to the project"),
    ("task_created", 12, 1, "created {title}"),
    ("task_moved", 28, 0, "moved {title} to In Progress"),
]


def _fixed(moment: datetime, hour: int, minute: int) -> datetime:
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)


def seed_demo_data(db: Session) -> None:
    """Populate an empty database with a realistic demo workspace."""
    if db.query(User.id).first() is not None:
        return

    now = datetime.now(timezone.utc)
    today = now.date()

    # ------------------------------------------------------------------ users
    users: list[User] = []
    for index, (email, full_name, job_title, avatar_color, bio) in enumerate(USERS):
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(DEMO_PASSWORD),
            job_title=job_title,
            avatar_color=avatar_color,
            bio=bio,
            is_active=True,
            created_at=_fixed(now - timedelta(days=90 - index * 4), 9, 15),
        )
        db.add(user)
        users.append(user)
    db.flush()

    # --------------------------------------------------------------- projects
    projects: list[Project] = []
    project_labels: list[list[Label]] = []
    member_indexes: list[list[int]] = []

    for index, (
        key,
        name,
        description,
        color,
        status,
        start_offset,
        due_offset,
        owner_index,
        members,
    ) in enumerate(PROJECTS):
        created_at = _fixed(now + timedelta(days=start_offset), 10, 0)
        project = Project(
            key=key,
            name=name,
            description=description,
            color=color,
            status=status,
            start_date=today + timedelta(days=start_offset),
            due_date=today + timedelta(days=due_offset),
            owner_id=users[owner_index].id,
            created_at=created_at,
            updated_at=_fixed(now - timedelta(days=index), 16, 30),
        )
        db.add(project)
        db.flush()
        projects.append(project)
        member_indexes.append([user_index for user_index, _ in members])

        for slot, (user_index, role) in enumerate(members):
            db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=users[user_index].id,
                    role=role,
                    joined_at=created_at + timedelta(hours=slot),
                )
            )

        labels = [
            Label(project_id=project.id, name=label_name, color=label_color)
            for label_name, label_color in LABELS
        ]
        db.add_all(labels)
        project_labels.append(labels)
    db.flush()

    # ------------------------------------------------------------------ tasks
    positions: dict[tuple[int, str], float] = {}
    tasks: list[Task] = []
    done_index = 0

    for index, (
        project_index,
        title,
        description,
        status,
        priority,
        assignee_index,
        due_offset,
        estimate,
    ) in enumerate(TASKS):
        project = projects[project_index]
        owner_index = PROJECTS[project_index][7]
        members = member_indexes[project_index]

        if status == "done":
            completed_days_ago = COMPLETION_OFFSETS[done_index % len(COMPLETION_OFFSETS)]
            created_days_ago = completed_days_ago + 3 + (done_index % 5)
            completed_at = _fixed(
                now - timedelta(days=completed_days_ago), 11 + (done_index % 7), 20
            )
            done_index += 1
        else:
            completed_days_ago = None
            created_days_ago = (index * 5 + 2) % 21
            completed_at = None

        created_at = min(
            _fixed(now - timedelta(days=created_days_ago), 8 + (index % 9), 45),
            now - timedelta(minutes=20 + index),
        )
        if completed_at is not None:
            updated_at = completed_at
        else:
            updated_at = min(
                created_at + timedelta(days=1 + (index % 4)),
                now - timedelta(hours=1 + (index % 20)),
            )
            updated_at = max(updated_at, created_at)

        reporter_index = owner_index
        if reporter_index == assignee_index:
            reporter_index = next(
                (candidate for candidate in members if candidate != assignee_index),
                owner_index,
            )

        position_key = (project.id, status)
        position = positions.get(position_key, 0.0) + 1000.0
        positions[position_key] = position

        task = Task(
            project_id=project.id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee_id=users[assignee_index].id,
            reporter_id=users[reporter_index].id,
            due_date=None if due_offset is None else today + timedelta(days=due_offset),
            estimate_hours=estimate,
            position=position,
            created_at=created_at,
            updated_at=updated_at,
            completed_at=completed_at,
        )

        labels = project_labels[project_index]
        task.labels.append(labels[index % len(labels)])
        if index % 3 == 0:
            task.labels.append(labels[(index + 2) % len(labels)])

        db.add(task)
        db.flush()
        tasks.append(task)

        # subtasks --------------------------------------------------------
        subtask_count = SUBTASK_COUNTS[index % len(SUBTASK_COUNTS)]
        if status == "done":
            done_cutoff = subtask_count
        elif status == "in_review":
            done_cutoff = max(subtask_count - 1, 0)
        elif status == "in_progress":
            done_cutoff = subtask_count // 2
        elif status == "todo":
            done_cutoff = 1 if subtask_count else 0
        else:
            done_cutoff = 0

        for slot in range(subtask_count):
            db.add(
                Subtask(
                    task_id=task.id,
                    title=SUBTASK_POOL[(index * 2 + slot) % len(SUBTASK_POOL)],
                    is_done=slot < done_cutoff,
                    created_at=created_at + timedelta(minutes=10 * (slot + 1)),
                )
            )

        # comments --------------------------------------------------------
        comment_count = COMMENT_COUNTS[index % len(COMMENT_COUNTS)]
        for slot in range(comment_count):
            author_index = members[(index + slot) % len(members)]
            posted_at = min(
                created_at + timedelta(days=slot + 1, hours=2 * slot + 1),
                now - timedelta(minutes=15 + slot * 5),
            )
            db.add(
                Comment(
                    task_id=task.id,
                    author_id=users[author_index].id,
                    body=COMMENT_POOL[(index * 3 + slot) % len(COMMENT_POOL)],
                    created_at=max(posted_at, created_at + timedelta(minutes=30)),
                )
            )

    # --------------------------------------------------------------- activity
    for index, project in enumerate(projects):
        owner_index = PROJECTS[index][7]
        db.add(
            Activity(
                project_id=project.id,
                task_id=None,
                actor_id=users[owner_index].id,
                action="project_created",
                summary=f"created the project {project.name}",
                meta={"project": project.name, "key": project.key},
                created_at=project.created_at,
            )
        )

    for slot, (action, task_index, actor_index, template) in enumerate(ACTIVITY_SPECS):
        task = tasks[task_index] if task_index is not None else None
        project_id = task.project_id if task is not None else projects[0].id
        summary = template.format(title=task.title if task is not None else "the project")
        db.add(
            Activity(
                project_id=project_id,
                task_id=task.id if task is not None else None,
                actor_id=users[actor_index].id,
                action=action,
                summary=summary,
                meta={"task_title": task.title} if task is not None else {},
                created_at=now - timedelta(hours=3 + slot * 11),
            )
        )

    db.commit()
