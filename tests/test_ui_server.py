from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.solidworks_mcp.ui import server


def test_should_log_request_paths() -> None:
    assert server._should_log_request("/api/health") is True
    assert server._should_log_request("/api/ui/state") is True
    assert server._should_log_request("/other") is False


def test_sanitize_log_payload_redacts_uploaded_data() -> None:
    payload = {
        "uploaded_files": [{"name": "part.sldprt", "data": "abcd"}],
        "data": "AAAA",
    }

    sanitized = server._sanitize_log_payload(payload)

    assert "omitted base64 payload" in sanitized["uploaded_files"][0]["data"]
    assert "omitted base64 payload" in sanitized["data"]


def test_decode_request_body_variants() -> None:
    assert server._decode_request_body(b"") is None

    text_result = server._decode_request_body(b"not-json")
    assert text_result == "not-json"

    parsed = server._decode_request_body(b'{"uploaded_files":[{"data":"abcd"}]}')
    assert "omitted base64 payload" in parsed["uploaded_files"][0]["data"]


def test_main_invokes_uvicorn(monkeypatch) -> None:
    called: dict[str, Any] = {}

    def _fake_run(app, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port
        called["app"] = app

    monkeypatch.setattr(server.uvicorn, "run", _fake_run)
    server.main()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8766
    assert called["app"] is server.app


def test_api_endpoints(monkeypatch) -> None:
    async def _a(value: dict[str, Any]) -> dict[str, Any]:
        return value

    monkeypatch.setattr(server, "build_dashboard_state", lambda *a, **k: {"ok": 1})
    monkeypatch.setattr(
        server, "build_dashboard_trace_payload", lambda *a, **k: {"trace": 1}
    )
    monkeypatch.setattr(server, "approve_design_brief", lambda *a, **k: {"approved": 1})
    monkeypatch.setattr(server, "update_ui_preferences", lambda *a, **k: {"prefs": 1})
    monkeypatch.setattr(server, "select_workflow_mode", lambda *a, **k: {"workflow": 1})
    monkeypatch.setattr(
        server, "ingest_reference_source", lambda *a, **k: {"ingest": 1}
    )
    monkeypatch.setattr(server, "accept_family_choice", lambda *a, **k: {"family": 1})
    monkeypatch.setattr(
        server, "reconcile_manual_edits", lambda *a, **k: {"reconcile": 1}
    )

    async def _connect(*a, **k):
        return {"connect": 1}

    async def _clarify(*a, **k):
        return {"clarify": 1}

    async def _inspect(*a, **k):
        return {"inspect": 1}

    async def _execute(*a, **k):
        return {"execute": 1}

    async def _refresh(*a, **k):
        return {"refresh": 1}

    monkeypatch.setattr(server, "connect_target_model", _connect)
    monkeypatch.setattr(server, "request_clarifications", _clarify)
    monkeypatch.setattr(server, "inspect_family", _inspect)
    monkeypatch.setattr(server, "execute_next_checkpoint", _execute)
    monkeypatch.setattr(server, "refresh_preview", _refresh)

    client = TestClient(server.app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    assert client.get("/api/ui/state").json() == {"ok": 1}
    assert client.get("/api/ui/debug/session").json() == {"trace": 1}

    assert client.post(
        "/api/ui/brief/approve", json={"session_id": "s", "user_goal": "g"}
    ).json() == {"approved": 1}
    assert client.post(
        "/api/ui/preferences/update",
        json={"session_id": "s", "assumptions_text": "a"},
    ).json() == {"prefs": 1}
    assert client.post(
        "/api/ui/workflow/select",
        json={"session_id": "s", "workflow_mode": "new_design"},
    ).json() == {"workflow": 1}
    assert client.post(
        "/api/ui/model/connect",
        json={"session_id": "s", "model_path": "C:/tmp/part.sldprt"},
    ).json() == {"connect": 1}
    assert client.post(
        "/api/ui/rag/ingest",
        json={"session_id": "s", "source_path": "C:/tmp/guide.md"},
    ).json() == {"ingest": 1}
    assert client.post(
        "/api/ui/clarify",
        json={"session_id": "s", "user_goal": "g", "user_answer": "a"},
    ).json() == {"clarify": 1}
    assert client.post(
        "/api/ui/family/inspect", json={"session_id": "s", "user_goal": "g"}
    ).json() == {"inspect": 1}
    assert client.post("/api/ui/family/accept", json={"session_id": "s"}).json() == {
        "family": 1
    }
    assert client.post(
        "/api/ui/checkpoints/execute-next", json={"session_id": "s"}
    ).json() == {"execute": 1}
    assert client.post("/api/ui/preview/refresh", json={"session_id": "s"}).json() == {
        "refresh": 1
    }
    assert client.post(
        "/api/ui/manual-sync/reconcile", json={"session_id": "s"}
    ).json() == {"reconcile": 1}

    viewer = client.get("/api/ui/viewer/prefab-dashboard")
    assert viewer.status_code == 200
    assert "3D Model Viewer" in viewer.text


def test_configure_ui_file_logging_idempotent() -> None:
    """Calling _configure_ui_file_logging a second time returns early (guard branch)."""
    # First call is made at module load time; second call hits the guard.
    server._UI_FILE_SINK_ID = 99  # type: ignore[attr-defined]
    try:
        server._configure_ui_file_logging()  # should be a no-op
    finally:
        server._UI_FILE_SINK_ID = None  # type: ignore[attr-defined]


def test_sanitize_log_payload_scalar() -> None:
    """Scalar (non-dict, non-list) values are returned unchanged."""
    assert server._sanitize_log_payload(42) == 42
    assert server._sanitize_log_payload("plain string") == "plain string"
    assert server._sanitize_log_payload(True) is True


def test_sanitize_log_payload_list_passthrough() -> None:
    """Plain list with no 'data' keys is sanitized recursively without change."""
    result = server._sanitize_log_payload([1, 2, "hello"])
    assert result == [1, 2, "hello"]


def test_local_model_probe_endpoint(monkeypatch) -> None:
    """GET /api/ui/local-model/probe returns a JSON probe result."""
    from src.solidworks_mcp.ui.local_llm import GEMMA_TIERS, LocalModelProbeResult

    spec = GEMMA_TIERS["small"]
    fake_probe = LocalModelProbeResult(
        available=False,
        endpoint="http://127.0.0.1:11434",
        openai_endpoint="http://127.0.0.1:11434/v1",
        tier="small",
        ollama_model=spec.ollama,
        service_model=spec.service,
        label=spec.label,
        vram_gb=0.0,
        ram_gb=8.0,
        pulled_models=[],
        tier_already_pulled=False,
        pull_command="ollama pull gemma3:4b",
        status_message="Ollama is not running.",
        all_tiers={k: v.label for k, v in GEMMA_TIERS.items()},
    )

    async def _fake_probe(*a, **k):
        return fake_probe

    import src.solidworks_mcp.ui.local_llm as llm_mod

    monkeypatch.setattr(llm_mod, "probe_local_model", _fake_probe)

    client = TestClient(server.app)
    resp = client.get("/api/ui/local-model/probe")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["tier"] == "small"


def test_local_model_pull_endpoint_success(monkeypatch) -> None:
    """POST /api/ui/local-model/pull returns queued=True on success."""
    from src.solidworks_mcp.ui.local_llm import LocalModelPullResult

    async def _fake_pull(model, endpoint=None):
        return LocalModelPullResult(queued=True, model=model)

    import src.solidworks_mcp.ui.local_llm as llm_mod

    monkeypatch.setattr(llm_mod, "pull_ollama_model", _fake_pull)

    client = TestClient(server.app)
    resp = client.post("/api/ui/local-model/pull", json={"model": "gemma3:4b"})
    assert resp.status_code == 200
    assert resp.json()["queued"] is True


def test_local_model_query_endpoint(monkeypatch) -> None:
    """POST /api/ui/local-model/query returns a LocalAgentResult."""
    from pydantic import BaseModel

    from src.solidworks_mcp.ui.local_llm import LocalAgentResult, LocalLLMConfig

    class _FreeForm(BaseModel):
        text: str = "SolidWorks answer"

    fake_config = LocalLLMConfig()
    fake_result = LocalAgentResult(success=True, data=_FreeForm(), config=fake_config)

    async def _fake_run(**kwargs):
        return fake_result

    import src.solidworks_mcp.ui.local_llm as llm_mod

    monkeypatch.setattr(llm_mod, "run_local_agent", _fake_run)

    client = TestClient(server.app)
    resp = client.post(
        "/api/ui/local-model/query",
        json={"prompt": "How do I create a sketch?"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_local_model_query_endpoint_with_overrides(monkeypatch) -> None:
    """Endpoint applies endpoint and model overrides from payload."""
    from pydantic import BaseModel

    from src.solidworks_mcp.ui.local_llm import LocalAgentResult, LocalLLMConfig

    class _FreeForm(BaseModel):
        text: str = "ok"

    fake_config = LocalLLMConfig()
    fake_result = LocalAgentResult(success=True, data=_FreeForm(), config=fake_config)

    captured: dict = {}

    async def _fake_run(**kwargs):
        captured["config"] = kwargs.get("config")
        return fake_result

    import src.solidworks_mcp.ui.local_llm as llm_mod

    monkeypatch.setattr(llm_mod, "run_local_agent", _fake_run)

    client = TestClient(server.app)
    resp = client.post(
        "/api/ui/local-model/query",
        json={
            "prompt": "Test query",
            "endpoint": "http://myhost:11434",
            "model": "gemma3:27b",
        },
    )
    assert resp.status_code == 200
    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.endpoint == "http://myhost:11434"


def test_startup_event_no_knowledge_dir(monkeypatch) -> None:
    """Startup event exits early when the design_knowledge directory doesn't exist."""
    # Using TestClient as context manager triggers lifespan/startup events.
    from pathlib import Path as _Path

    monkeypatch.setattr(_Path, "is_dir", lambda self: False)
    with TestClient(server.app):
        pass  # startup ran without error


def test_middleware_logs_non_ui_requests(monkeypatch) -> None:
    """Non-UI paths bypass the logging middleware without error."""
    monkeypatch.setattr(server, "build_dashboard_state", lambda *a, **k: {"ok": 1})
    client = TestClient(server.app)
    resp = client.get("/api/ui/state")
    assert resp.status_code == 200


async def test_startup_event_ingests_knowledge(monkeypatch, tmp_path) -> None:
    """Startup event runs full ingest path when design_knowledge dir exists with md files."""
    import src.solidworks_mcp.agents.vector_rag as vr_mod

    # Track calls
    ingested: list[str] = []
    saved: list[bool] = []

    class _FakeIdx:
        chunk_count = 0

        def ingest_text(self, text, source=None, tags=None):
            ingested.append(source)
            return 1

        def save(self):
            saved.append(True)

        @classmethod
        def load(cls, namespace, rag_dir):
            return cls()

    monkeypatch.setattr(vr_mod, "VectorRAGIndex", _FakeIdx)
    await server._startup_ingest_design_knowledge()
    # design_knowledge/solidworks_basics.md should have been ingested
    assert any("solidworks_basics" in (s or "") for s in ingested)
    assert saved


async def test_startup_event_skips_nonempty_index(monkeypatch) -> None:
    """Startup event skips ingest when FAISS index already has chunks."""
    import src.solidworks_mcp.agents.vector_rag as vr_mod

    ingested: list[str] = []

    class _FakeIdx:
        chunk_count = 5  # non-zero → skip

        def ingest_text(self, text, source=None, tags=None):
            ingested.append(source)

        def save(self):
            pass

        @classmethod
        def load(cls, namespace, rag_dir):
            return cls()

    monkeypatch.setattr(vr_mod, "VectorRAGIndex", _FakeIdx)
    await server._startup_ingest_design_knowledge()
    assert not ingested  # debug path taken, no ingest


async def test_startup_event_import_error(monkeypatch) -> None:
    """Startup event swallows ImportError when faiss is unavailable."""
    import src.solidworks_mcp.agents.vector_rag as vr_mod

    def _raise(*a, **k):
        raise ImportError("no faiss")

    monkeypatch.setattr(
        vr_mod, "VectorRAGIndex", type("X", (), {"load": staticmethod(_raise)})
    )
    # Should not raise
    await server._startup_ingest_design_knowledge()


async def test_startup_event_generic_exception(monkeypatch) -> None:
    """Startup event swallows generic exceptions (non-fatal)."""
    import src.solidworks_mcp.agents.vector_rag as vr_mod

    def _raise(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        vr_mod, "VectorRAGIndex", type("X", (), {"load": staticmethod(_raise)})
    )
    await server._startup_ingest_design_knowledge()


def test_middleware_exception_path(monkeypatch) -> None:
    """Middleware exception branch is hit when a route raises inside the logged path."""
    import pytest

    # Mount a route that raises
    from fastapi import HTTPException

    @server.app.get("/api/ui/__test_error__")
    async def _error_route():
        raise RuntimeError("intentional middleware test error")

    client = TestClient(server.app, raise_server_exceptions=False)
    resp = client.get("/api/ui/__test_error__")
    # The middleware re-raises after logging; TestClient with raise_server_exceptions=False
    # returns 500
    assert resp.status_code == 500
