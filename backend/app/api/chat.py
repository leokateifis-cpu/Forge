"""
Chat endpoint — hypothesis interview (Stage 1) and general assistant.

Streams responses via SSE. The LLM is in constrained mode until the hypothesis
JSON block appears in its output, at which point the hypothesis is auto-saved.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import json

from app.db.base import get_db
from app.models.project import Project, ProjectStage, StageEvent
from app.models.message import Message
from app.models.hypothesis import Hypothesis
from app.models.user import User
from app.core.security import get_current_user
from app.services.llm import run_hypothesis_chat, parse_hypothesis_from_response, generate_strategy_code

router = APIRouter()


class ChatRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str

    class Config:
        from_attributes = True


@router.get("/messages", response_model=list[MessageResponse])
def get_messages(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)
    return db.query(Message).filter(Message.project_id == project.id).order_by(Message.created_at).all()


@router.post("/send")
async def send_message(
    project_id: UUID,
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)

    # Store user message
    user_msg = Message(project_id=project.id, role="user", content=req.content)
    db.add(user_msg)
    db.commit()

    # Build message history for LLM
    history = db.query(Message).filter(Message.project_id == project.id).order_by(Message.created_at).all()
    llm_messages = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]

    async def stream():
        full_response = ""
        async for chunk in run_hypothesis_chat(llm_messages):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

        # Save assistant response
        asst_msg = Message(project_id=project.id, role="assistant", content=full_response)
        db.add(asst_msg)

        # Check if hypothesis is complete
        hypothesis_data = parse_hypothesis_from_response(full_response)
        if hypothesis_data and project.current_stage == ProjectStage.HYPOTHESIS:
            hyp = Hypothesis(
                project_id=project.id,
                instrument=hypothesis_data.get("instrument"),
                timeframe=hypothesis_data.get("timeframe"),
                entry_rule=hypothesis_data.get("entry_rule"),
                exit_rule=hypothesis_data.get("exit_rule"),
                direction=hypothesis_data.get("direction"),
                expected_holding_period=hypothesis_data.get("expected_holding_period"),
                claim=hypothesis_data.get("claim"),
                falsification_condition=hypothesis_data.get("falsification_condition"),
                raw_json=hypothesis_data,
            )
            db.add(hyp)

            # Update project instrument/timeframe
            project.instrument = hypothesis_data.get("instrument", project.instrument)
            project.timeframe = hypothesis_data.get("timeframe", project.timeframe)

            db.commit()
            yield f"data: {json.dumps({'type': 'hypothesis_ready', 'data': hypothesis_data})}\n\n"
        else:
            db.commit()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/confirm-hypothesis")
def confirm_hypothesis(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm the latest hypothesis and advance to Stage 2 (code generation)."""
    project = _get_project(project_id, user.id, db)

    if project.current_stage != ProjectStage.HYPOTHESIS:
        raise HTTPException(400, "Project is not in hypothesis stage")

    hyp = db.query(Hypothesis).filter(
        Hypothesis.project_id == project.id,
        Hypothesis.confirmed == False,
    ).order_by(Hypothesis.created_at.desc()).first()

    if not hyp:
        raise HTTPException(400, "No hypothesis to confirm")

    hyp.confirmed = True
    hyp.confirmed_at = datetime.utcnow()
    project.current_stage = ProjectStage.CODE

    event = StageEvent(project_id=project.id, stage=ProjectStage.HYPOTHESIS, action="completed")
    db.add(event)
    db.commit()

    return {"status": "confirmed", "next_stage": ProjectStage.CODE}


def _get_project(project_id: UUID, user_id, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p
