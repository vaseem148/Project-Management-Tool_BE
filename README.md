# Nexus PM — Backend

FastAPI + SQLAlchemy + SQLite API for the Nexus PM project-management app.
Auth is JWT bearer; everything except register/login requires an `Authorization: Bearer <token>` header.

## Quick start

### Windows (PowerShell)

```powershell
cd pmt_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

### macOS / Linux

```bash
cd pmt_backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The API is served on <http://127.0.0.1:8010>:

- Swagger UI — <http://127.0.0.1:8010/docs>
- ReDoc — <http://127.0.0.1:8010/redoc>
- Health check — <http://127.0.0.1:8010/api/health>

The Vite dev server proxies `/api` to this port, so start the backend first and then run
`npm run dev` inside `pmt_frontend`.

## Demo login

On the first start (empty database) a demo workspace is inserted: 6 teammates, 4 projects,
46 tasks with subtasks and comments, and an activity feed spread over the last three weeks.

| Field    | Value          |
| -------- | -------------- |
| Email    | `demo@pmt.app` |
| Password | `demo1234`     |

Every seeded teammate uses the same password (`priya@pmt.app`, `rahul@pmt.app`, `sara@pmt.app`,
`diego@pmt.app`, `mei@pmt.app`). The seeder is a no-op as soon as one user row exists — delete
`pmt.db` to get a fresh workspace, or set `SEED_DEMO_DATA=false` to start empty.

## Configuration

Copy `.env.example` to `.env` to override anything. Defaults live in `app/core/config.py`:
SQLite at `pmt_backend/pmt.db`, a 7-day token lifetime, and CORS open to the Vite dev/preview ports.

## Endpoints

All paths are prefixed with `/api`.

### Auth & users

| Method   | Path             | Body          | Returns             | Notes                       |
| -------- | ---------------- | ------------- | ------------------- | --------------------------- |
| `POST`   | `/auth/register` | `UserCreate`  | `TokenResponse`     | 409 when the email is taken |
| `POST`   | `/auth/login`    | `LoginRequest`| `TokenResponse`     | 401 on bad credentials      |
| `GET`    | `/auth/me`       | —             | `UserPublic`        | Current user                |
| `PATCH`  | `/auth/me`       | `UserUpdate`  | `UserPublic`        | Profile edit                |
| `GET`    | `/users?q=`      | —             | `UserPublic[]`      | Active users, for pickers   |

### Projects

| Method   | Path                                     | Body            | Returns          | Notes                          |
| -------- | ---------------------------------------- | --------------- | ---------------- | ------------------------------ |
| `GET`    | `/projects?q=&status=`                   | —               | `ProjectPublic[]`| Owned or joined, stats filled  |
| `POST`   | `/projects`                              | `ProjectCreate` | `ProjectPublic`  | Seeds 4 default labels         |
| `GET`    | `/projects/{project_id}`                 | —               | `ProjectPublic`  |                                |
| `PATCH`  | `/projects/{project_id}`                 | `ProjectUpdate` | `ProjectPublic`  | Admin only                     |
| `DELETE` | `/projects/{project_id}`                 | —               | `Message`        | Owner only                     |
| `GET`    | `/projects/{project_id}/members`         | —               | `MemberPublic[]` |                                |
| `POST`   | `/projects/{project_id}/members`         | `MemberCreate`  | `MemberPublic`   | Admin only, 409 on duplicate   |
| `PATCH`  | `/projects/{project_id}/members/{user_id}`| `MemberUpdate` | `MemberPublic`   | Admin only                     |
| `DELETE` | `/projects/{project_id}/members/{user_id}`| —              | `Message`        | Admin only, never the owner    |
| `GET`    | `/projects/{project_id}/labels`          | —               | `LabelPublic[]`  |                                |
| `POST`   | `/projects/{project_id}/labels`          | `LabelCreate`   | `LabelPublic`    | Editors only                   |
| `DELETE` | `/labels/{label_id}`                     | —               | `Message`        | Editors only                   |
| `GET`    | `/projects/{project_id}/stats`           | —               | `ProjectStats`   |                                |

### Tasks

| Method   | Path                        | Body            | Returns         | Notes                                   |
| -------- | --------------------------- | --------------- | --------------- | --------------------------------------- |
| `GET`    | `/tasks`                    | —               | `TaskPublic[]`  | Filters below                           |
| `POST`   | `/tasks`                    | `TaskCreate`    | `TaskPublic`    | Editors only, reporter = current user   |
| `GET`    | `/tasks/{task_id}`          | —               | `TaskDetail`    | With subtasks + comments                |
| `PATCH`  | `/tasks/{task_id}`          | `TaskUpdate`    | `TaskPublic`    | Sets/clears `completed_at`              |
| `DELETE` | `/tasks/{task_id}`          | —               | `Message`       |                                         |
| `POST`   | `/tasks/{task_id}/move`     | `TaskMove`      | `TaskPublic`    | Drag & drop; null position appends      |
| `POST`   | `/tasks/{task_id}/subtasks` | `SubtaskCreate` | `SubtaskPublic` |                                         |
| `PATCH`  | `/subtasks/{subtask_id}`    | `SubtaskUpdate` | `SubtaskPublic` |                                         |
| `DELETE` | `/subtasks/{subtask_id}`    | —               | `Message`       |                                         |
| `GET`    | `/tasks/{task_id}/comments` | —               | `CommentPublic[]`|                                        |
| `POST`   | `/tasks/{task_id}/comments` | `CommentCreate` | `CommentPublic` |                                         |
| `DELETE` | `/comments/{comment_id}`    | —               | `Message`       | Author or project admin                 |

`GET /tasks` query parameters: `project_id`, `status` (repeatable), `priority` (repeatable),
`assignee_id`, `label_id`, `q`, `due` (`overdue` \| `today` \| `week`), `mine` (bool),
`sort` (`position` \| `due_date` \| `priority` \| `created_at`, default `position`), `limit` (default 500).

### Dashboard & activity

| Method | Path                            | Returns            | Notes                                          |
| ------ | ------------------------------- | ------------------ | ---------------------------------------------- |
| `GET`  | `/dashboard/summary`            | `DashboardSummary` | Aggregates over every visible project          |
| `GET`  | `/activity?project_id=&limit=30`| `ActivityPublic[]` | Newest first, `limit` 1-200                    |
| `GET`  | `/health`                       | `{"status":"ok"}`  | No auth required                               |

`DashboardSummary` contains the headline counters (`total_projects`, `active_projects`,
`total_tasks`, `my_open_tasks`, `completed_tasks`, `overdue_tasks`, `due_soon_tasks`,
`completion_rate`), `tasks_by_status` / `tasks_by_priority` buckets, a 14-day `trend`
(`{date, created, completed}`), the top 6 assignees by `workload`, the next 6 `upcoming`
due tasks, the latest 8 `recent_activity` entries and the full `projects` list.

## Layout

```
pmt_backend/
  app/
    api/
      deps.py            auth + permission dependencies
      routes/            auth, users, projects, tasks, dashboard
    core/                config, database, security
    models/entities.py   SQLAlchemy models
    schemas/             Pydantic request/response models
    services/
      serializers.py     ORM -> schema helpers, activity logging
      seed.py            deterministic demo workspace
    main.py              FastAPI app, CORS, router wiring, lifespan
  run.py                 uvicorn dev server
```
