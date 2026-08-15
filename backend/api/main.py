"""FastAPI wrapper around InsurabilityAgent, for the Next.js chat UI.

Deliberately thin — all reasoning, tool-use, and scoring stays in
agent/agent.py and its backend. This layer's only job is session
management (one InsurabilityAgent per browser session, in-memory — fine
for a hackathon demo, not meant to survive a server restart) and turning
HTTP requests into agent.ask_verbose() calls.
"""

from __future__ import annotations

import logging
import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent.agent import InsurabilityAgent  # noqa: E402

logger = logging.getLogger("insurability_api")

app = FastAPI(title="Insurability Triage Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch-all. agent.ask_verbose() already degrades gracefully
    on its own known failure modes (API errors, runaway loops, tool crashes)
    — this exists for the unexpected case, so a client always gets clean
    JSON back instead of a bare 500 or a hung connection."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on the server. Please try again."},
    )

# session_id -> InsurabilityAgent. In-memory by design (Next Steps: swap
# for Redis/a real store if this ever runs multi-instance).
_sessions: dict[str, InsurabilityAgent] = {}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list[dict]


class ResetRequest(BaseModel):
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    session_id = req.session_id or str(uuid.uuid4())
    agent = _sessions.get(session_id)
    if agent is None:
        try:
            agent = InsurabilityAgent(verbose=False)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        _sessions[session_id] = agent

    result = agent.ask_verbose(req.message)
    return ChatResponse(
        session_id=session_id,
        reply=result["reply"],
        tool_calls=result["tool_calls"],
    )


@app.post("/chat/reset")
def reset(req: ResetRequest):
    _sessions.pop(req.session_id, None)
    return {"ok": True}
