"""FastAPI entrypoint for Nexus PM."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.api.routes import auth, dashboard, projects, tasks, users
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.services.seed import seed_demo_data


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    if settings.SEED_DEMO_DATA:
        db = SessionLocal()
        try:
            seed_demo_data(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Projects, boards and tasks for the Nexus PM workspace.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1)
app.include_router(users.router, prefix=settings.API_V1)
app.include_router(projects.router, prefix=settings.API_V1)
app.include_router(projects.label_router, prefix=settings.API_V1)
app.include_router(tasks.router, prefix=settings.API_V1)
app.include_router(tasks.subtask_router, prefix=settings.API_V1)
app.include_router(tasks.comment_router, prefix=settings.API_V1)
app.include_router(dashboard.router, prefix=settings.API_V1)
app.include_router(dashboard.activity_router, prefix=settings.API_V1)


@app.get(f"{settings.API_V1}/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.APP_NAME, "docs": "/docs", "health": f"{settings.API_V1}/health"}
