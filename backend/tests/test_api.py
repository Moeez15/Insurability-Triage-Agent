from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app


class _FakeAgent:
    """Stands in for InsurabilityAgent so these tests exercise only the
    FastAPI layer — session handling, validation, error responses — not
    the real Anthropic/Mireye calls (those are covered in test_agent.py
    and test_mireye_client.py)."""

    def __init__(self, *_args, **_kwargs):
        pass

    def ask_verbose(self, message: str) -> dict:
        if message == "CRASH":
            raise RuntimeError("simulated unexpected crash")
        return {"reply": f"echo: {message}", "tool_calls": []}


def _client(monkeypatch, raise_server_exceptions: bool = True):
    monkeypatch.setattr(api_main, "InsurabilityAgent", _FakeAgent)
    api_main._sessions.clear()
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_happy_path(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "echo: hello"
    assert "session_id" in body


def test_chat_rejects_empty_message(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422  # pydantic min_length=1


def test_chat_rejects_whitespace_only_message(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/chat", json={"message": "   "})
    assert resp.status_code == 400


def test_chat_rejects_oversized_message(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/chat", json={"message": "a" * 3000})
    assert resp.status_code == 422


def test_session_persists_across_calls(monkeypatch):
    client = _client(monkeypatch)
    first = client.post("/chat", json={"message": "hello"}).json()
    session_id = first["session_id"]
    second = client.post(
        "/chat", json={"message": "again", "session_id": session_id}
    ).json()
    assert second["session_id"] == session_id
    assert len(api_main._sessions) == 1


def test_chat_reset_clears_session(monkeypatch):
    client = _client(monkeypatch)
    first = client.post("/chat", json={"message": "hello"}).json()
    session_id = first["session_id"]
    assert session_id in api_main._sessions

    resp = client.post("/chat/reset", json={"session_id": session_id})
    assert resp.status_code == 200
    assert session_id not in api_main._sessions


def test_unhandled_exception_returns_clean_500(monkeypatch):
    """An unexpected crash inside the agent must not leak a raw traceback
    — the global exception handler should degrade to a clean JSON error."""
    client = _client(monkeypatch, raise_server_exceptions=False)
    resp = client.post("/chat", json={"message": "CRASH"})
    assert resp.status_code == 500
    assert resp.json() == {
        "detail": "Something went wrong on the server. Please try again."
    }


def test_agent_init_failure_returns_500(monkeypatch):
    def broken_init(*_a, **_kw):
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    monkeypatch.setattr(api_main, "InsurabilityAgent", broken_init)
    api_main._sessions.clear()
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 500
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]
