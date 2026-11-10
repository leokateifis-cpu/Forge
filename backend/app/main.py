from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import auth, projects, chat, pipeline, reports, account_setup, papers

settings = get_settings()

app = FastAPI(
    title="Forge API",
    description="Guided quantitative research platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(chat.router, prefix="/api/projects/{project_id}/chat", tags=["chat"])
app.include_router(pipeline.router, prefix="/api/projects/{project_id}/pipeline", tags=["pipeline"])
app.include_router(reports.router, prefix="/api/projects/{project_id}/report", tags=["reports"])
app.include_router(account_setup.router, prefix="/api/account", tags=["account"])
app.include_router(papers.router, prefix="/api/papers", tags=["papers"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
