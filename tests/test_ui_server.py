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
