"""Chatbot endpoints: POST /ai/chat and POST /ai/chat/confirm (login required)."""
import json
import logging
import re
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.ai.agent.graph import build_graph
from app.api.deps import get_current_user
from app.models import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai-chat"])

THREAD_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_graph = None
_graph_lock = threading.Lock()
_thread_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def get_graph():
    """One shared graph (and one in-memory checkpointer) for the whole process."""
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = build_graph()
        return _graph


def _thread_lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _thread_locks.setdefault(key, threading.Lock())


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    thread_id: str | None = None


class ConfirmIn(BaseModel):
    thread_id: str
    confirm: bool


class ChatChef(BaseModel):
    id: int
    name: str
    photo: str | None = None
    city: str | None = None
    rating: float = 0.0
    price: float = 0.0
    match: int = 0
    estimate: int = 0
    reason: str = ""
    factors: list[dict] = []  # "why this rank?" contributions from the ML model


class ChatOut(BaseModel):
    thread_id: str
    reply: str
    pending_confirmation: dict | None = None
    chefs: list[ChatChef] = []
    ranked_by: str | None = None  # "ml" or "rules"


def _check_thread_id(thread_id: str) -> None:
    if not THREAD_RE.match(thread_id):
        raise HTTPException(422, "thread_id must be 8-64 letters, digits, '-' or '_'")


def _config(user: User, thread_id: str) -> tuple[str, dict]:
    key = f"u{user.id}:{thread_id}"  # namespaced so users cannot reach each other's threads
    return key, {"configurable": {"thread_id": key, "user_id": user.id}}


def _pending(graph, config: dict) -> dict | None:
    for task in graph.get_state(config).tasks:
        for item in task.interrupts:
            return item.value
    return None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)


def _last_reply(graph, config: dict) -> str:
    for m in reversed(graph.get_state(config).values.get("messages", [])):
        if m.type == "ai" and not getattr(m, "tool_calls", None):
            return _text(m.content).strip()
    return ""


def _turn_chefs(graph, config: dict) -> tuple[list[ChatChef], str | None]:
    """Chef cards come from the latest search_chefs RESULT in this turn, not from the model's text."""
    found = None
    for m in reversed(graph.get_state(config).values.get("messages", [])):
        if m.type == "human":
            break  # only look at the current turn
        if m.type == "tool" and getattr(m, "name", None) == "search_chefs" and found is None:
            try:
                found = json.loads(_text(m.content))
            except (ValueError, TypeError):
                found = None
    if not isinstance(found, dict):
        return [], None
    chefs = []
    for c in (found.get("chefs") or [])[:5]:
        try:
            chefs.append(ChatChef(
                id=c["chef_id"], name=c["name"], photo=c.get("photo"), city=c.get("city"),
                rating=c.get("rating") or 0, price=c.get("base_price") or 0,
                match=c.get("match_percent") or 0, estimate=c.get("estimated_price") or 0,
                reason=" · ".join(c.get("reasons") or []),
                factors=c.get("factors") or []))
        except (KeyError, ValueError):
            continue
    return chefs, found.get("ranked_by")


def _run(user: User, thread_id: str, make_input, require_pending: bool) -> ChatOut:
    key, config = _config(user, thread_id)
    lock = _thread_lock(key)
    if not lock.acquire(blocking=False):
        raise HTTPException(429, "Still working on your previous message. Please wait a moment.")
    try:
        graph = get_graph()
        pending = _pending(graph, config)

        if require_pending and not pending:
            raise HTTPException(409, "There is no booking waiting for confirmation.")
        if not require_pending and pending:  # user typed instead of confirming: show it again
            return ChatOut(thread_id=thread_id, pending_confirmation=pending,
                           reply="Please confirm or cancel this booking first.")

        graph.invoke(make_input(), config)
        pending = _pending(graph, config)
        if pending:
            return ChatOut(thread_id=thread_id, pending_confirmation=pending,
                           reply="Please review and confirm this booking.")
        chefs, ranked_by = _turn_chefs(graph, config)
        return ChatOut(thread_id=thread_id, reply=_last_reply(graph, config) or "Sorry, I could not answer that.",
                       chefs=chefs, ranked_by=ranked_by)
    except HTTPException:
        raise
    except Exception:
        log.exception("chatbot failed")
        raise HTTPException(503, "The assistant is unavailable right now. Please try again.")
    finally:
        lock.release()


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(get_current_user)):
    thread_id = body.thread_id or uuid.uuid4().hex
    _check_thread_id(thread_id)
    return _run(user, thread_id, lambda: {"messages": [("user", body.message)]}, require_pending=False)


@router.post("/chat/confirm", response_model=ChatOut)
def confirm(body: ConfirmIn, user: User = Depends(get_current_user)):
    _check_thread_id(body.thread_id)
    return _run(user, body.thread_id, lambda: Command(resume=body.confirm), require_pending=True)
