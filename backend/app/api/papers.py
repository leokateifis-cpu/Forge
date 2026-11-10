"""
Research Paper Terminal — search arXiv/SSRN, extract trading rules, test on ES/NQ data.

The terminal:
  1. Searches arXiv (q-fin section) using the OpenAI API to form a targeted query.
  2. Fetches paper metadata from the arXiv API.
  3. Reads the abstract and available full text.
  4. Extracts the trading signal description.
  5. Generates strategy code for the described method.
  6. Tests on built-in ES/NQ data.
  7. Returns ranked results.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx
import json

from app.db.base import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.core.config import get_settings
from app.tasks.paper_tasks import run_paper_search_task
from app.models.job import Job, JobStatus, JobType

settings = get_settings()
router = APIRouter()


class PaperSearchRequest(BaseModel):
    query: str


@router.post("/search")
def search_papers(
    req: PaperSearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enqueue a paper search + test job. Returns job_id to poll."""
    job = Job(
        project_id=None,  # Papers aren't tied to a project
        job_type=JobType.PAPER_TEST,
    )
    # Note: project_id is nullable for paper jobs
    from app.models.job import Job as JobModel
    from sqlalchemy import Column, String
    job_model = JobModel.__new__(JobModel)
    job_model.__dict__.update({
        "job_type": JobType.PAPER_TEST,
        "status": JobStatus.PENDING,
    })

    # Use a simple approach: run synchronously for now, async in production
    task = run_paper_search_task.delay(req.query, str(user.id))
    return {"task_id": task.id, "status": "queued"}


@router.get("/job/{task_id}")
def get_paper_job(task_id: str, user: User = Depends(get_current_user)):
    """Poll for paper search results."""
    from app.tasks.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)

    if result.state == "PENDING":
        return {"status": "pending"}
    elif result.state == "STARTED":
        return {"status": "running"}
    elif result.state == "SUCCESS":
        return {"status": "success", "results": result.result}
    elif result.state == "FAILURE":
        return {"status": "failed", "error": str(result.info)}
    return {"status": result.state}
