"""Tests for test ui service branches."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.solidworks_mcp.agents.schemas import RecoverableFailure
from src.solidworks_mcp.ui import service


class _Result:
    """Test result."""

    def __init__(
        self, *, is_success: bool = True, data: Any = None, error: str | None = None
    ):
        """Test init."""

        self.is_success = is_success
        self.data = data
        self.error = error


class _Headers:
    """Test headers."""

    def __init__(self, content_type: str, charset: str = "utf-8") -> None:
        """Test init."""

        self._content_type = content_type
        self._charset = charset

    def get_content_type(self) -> str:
        """Test get content type."""

        return self._content_type

    def get_content_charset(self) -> str:
        """Test get content charset."""

        return self._charset


class _Resp:
    """Test resp."""

    def __init__(self, body: bytes, content_type: str, charset: str = "utf-8") -> None:
        """Test init."""

        self._body = body
        self.headers = _Headers(content_type, charset)

    def read(self) -> bytes:
        """Test read."""

        return self._body

    def __enter__(self) -> _Resp:
        """Test enter."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Test exit."""

        return False


def test_ui_service_helper_branches_text_provider_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ui service helper branches text provider trace."""

    assert service._parse_json_blob("[") == {}
    assert service._parse_json_blob("[]") == {}

    assert service._sanitize_ui_text('"', "fallback") == "fallback"
    assert service._sanitize_ui_text("{{ bad }}", "fallback") == "fallback"
    assert service._sanitize_ui_text("$error value", "fallback") == "fallback"

    assert service._provider_from_model_name("openai:gpt") == "openai"
    assert service._provider_from_model_name("anthropic:claude") == "anthropic"
    assert service._provider_from_model_name("local:model") == "local"
    assert service._provider_from_model_name("x") == "custom"

    assert service._default_model_for_profile("local", "small").startswith("local:")
    assert service._default_model_for_profile("local", "unknown").startswith("local:")
    assert service._default_model_for_profile("github", "small").startswith("github:")

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert service._provider_has_credentials("openai:gpt") is True
    assert service._provider_has_credentials("anthropic:claude") is True
    assert (
        service._provider_has_credentials(
            "local:model", local_endpoint="http://127.0.0.1"
        )
        is True
    )
    assert service._provider_has_credentials("custom:model") is True

    assert service._workflow_copy("new_design")[0] == "New Design From Scratch"
    assert "already attached" in service._workflow_copy("other", "C:/part.sldprt")[1]

    traced = service._trace_json({"path": Path("a/b")})
    assert "path" in traced
    assert service._trace_session_row({"id": 1, "metadata_json": "{}"}) == {"id": 1}
    assert service._trace_session_row(None) == {}
    assert (
        service._trace_tool_records([{"id": 1, "tool_name": "x"}])[0]["tool_name"]
        == "x"
    )


def test_ui_service_feature_target_status_branches() -> None:
    """Test ui service feature target status branches."""

    features = [{"name": "Boss-Extrude1"}, {"name": "Sketch1"}]
    full = service._feature_target_status(features, "@Boss-Extrude1")
    assert "Grounded" in full[0]

    partial = service._feature_target_status(features, "@Boss-Extrude1,@Missing")
    assert "Partially grounded" in partial[0]

    none = service._feature_target_status(features, "@Missing")
    assert "No matching" in none[0]


def test_ui_service_reference_url_pdf_and_source_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test ui service reference url pdf and source text."""

    txt = tmp_path / "guide.md"
    txt.write_text("hello", encoding="utf-8")
    assert service._read_reference_source(txt) == "hello"

    class _PdfReader:
        """Test pdf reader."""

        def __init__(self, _stream: Any) -> None:
            """Test init."""

            self.pages = [SimpleNamespace(extract_text=lambda: "page-one")]

    monkeypatch.setattr(service, "PdfReader", _PdfReader)
    monkeypatch.setattr(
        service,
        "urlopen",
        lambda request, timeout=20: _Resp(b"%PDF-1.4", "application/pdf"),
    )

    text, label = service._read_reference_url("https://example.com/file.pdf")
    assert text == "page-one"
    assert label == "file.pdf"


def test_ui_service_build_agent_model_local_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ui service build agent model local success."""

    class _Provider:
        """Test provider."""

        def __init__(self, *, base_url: str, api_key: str) -> None:
            """Test init."""

            self.base_url = base_url
            self.api_key = api_key

    class _ChatModel:
        """Test chat model."""

        def __init__(self, model: str, provider: Any) -> None:
            """Test init."""

            self.model = model
            self.provider = provider

    monkeypatch.setattr(service, "OpenAIProvider", _Provider)
    monkeypatch.setattr(service, "OpenAIChatModel", _ChatModel)

    model = service._build_agent_model("local:my-model", "http://127.0.0.1:11434/v1")
    assert model.model == "my-model"
    assert model.provider.base_url.endswith("/v1")


def test_ui_service_ensure_provider_credentials_github_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ui service ensure provider credentials github failure."""

    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)

    def _raise(*_a: Any, **_k: Any) -> Any:
        """Test raise."""

        raise RuntimeError("gh missing")

    monkeypatch.setattr(service.subprocess, "run", _raise)

    with pytest.raises(RuntimeError, match="Set GH_TOKEN"):
        service._ensure_provider_credentials("github:openai/gpt-4.1")


@pytest.mark.asyncio
async def test_ui_service_run_structured_agent_success_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ui service run structured agent success variants."""

    class _AgentWithData:
        """Test agent with data."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Test init."""

            self.args = args
            self.kwargs = kwargs

        async def run(self, _prompt: str) -> Any:
            """Test run."""

            return SimpleNamespace(
                data={"normalized_brief": "brief text", "questions": ["q1"]}
            )

    monkeypatch.setattr(service, "Agent", _AgentWithData)
    monkeypatch.setattr(service, "_ensure_provider_credentials", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "_build_agent_model", lambda *_a, **_k: "model")

    payload = await service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=service.ClarificationResponse,
    )
    assert isinstance(payload, service.ClarificationResponse)

    class _AgentWithOutput(_AgentWithData):
        """Test agent with output."""

        async def run(self, _prompt: str) -> Any:
            """Test run."""

            return SimpleNamespace(
                output=service.ClarificationResponse(
                    normalized_brief="normalized brief", questions=[]
                )
            )

    monkeypatch.setattr(service, "Agent", _AgentWithOutput)
    payload2 = await service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=service.ClarificationResponse,
    )
    assert payload2.normalized_brief == "normalized brief"


@pytest.mark.asyncio
async def test_ui_service_execute_next_checkpoint_no_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ui service execute next checkpoint no target."""

    monkeypatch.setattr(
        service, "ensure_dashboard_session", lambda *_a, **_k: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        service, "list_plan_checkpoints", lambda *_a, **_k: [{"executed": True}]
    )
    monkeypatch.setattr(
        service, "build_dashboard_state", lambda *_a, **_k: {"ok": True}
    )

    captured: dict[str, Any] = {}

    def _merge(*_a: Any, **kwargs: Any) -> dict[str, Any]:
        """Test merge."""

        captured.update(kwargs)
        return {}

    monkeypatch.setattr(service, "_merge_metadata", _merge)
    out = await service.execute_next_checkpoint("s")
    assert out == {"ok": True}
    assert "All checkpoints" in captured["latest_message"]


@pytest.mark.asyncio
async def test_ui_service_connect_target_model_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test ui service connect target model error paths."""

    db_path = tmp_path / "ui.sqlite3"
    service.ensure_dashboard_session("s-connect", db_path=db_path)

    no_input = await service.connect_target_model("s-connect", db_path=db_path)
    assert "No target model" in no_input["latest_message"]

    missing = await service.connect_target_model(
        "s-connect",
        model_path=str(tmp_path / "missing.sldprt"),
        db_path=db_path,
    )
    assert "not found" in missing["latest_message"]

    part = tmp_path / "part.sldprt"
    part.write_text("x", encoding="utf-8")

    class _OpenFailAdapter:
        """Test open fail adapter."""

        async def connect(self) -> None:
            """Test connect."""

            return None

        async def disconnect(self) -> None:
            """Test disconnect."""

            return None

        async def open_model(self, _path: str) -> _Result:
            """Test open model."""

            return _Result(is_success=False, error="open failed")

    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())

    async def _create_adapter(_config: Any) -> Any:
        """Test create adapter."""

        return _OpenFailAdapter()

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    failed = await service.connect_target_model(
        "s-connect", model_path=str(part), db_path=db_path
    )
    assert "Failed to attach target model" in failed["latest_message"]


def test_ui_service_ingest_reference_source_error_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test ui service ingest reference source error branches."""

    db_path = tmp_path / "ui.sqlite3"
    service.ensure_dashboard_session("s-rag", db_path=db_path)

    missing = service.ingest_reference_source(
        "s-rag",
        source_path=str(tmp_path / "none.md"),
        namespace="",
        db_path=db_path,
    )
    assert "not found" in missing["rag_status"].lower()

    src = tmp_path / "src.md"
    src.write_text("hello world", encoding="utf-8")

    def _raise_chunk(*_a: Any, **_k: Any) -> Any:
        """Test raise chunk."""

        raise RuntimeError("chunk failure")

    monkeypatch.setattr(service, "_chunk_text", _raise_chunk)
    failed = service.ingest_reference_source(
        "s-rag",
        source_path=str(src),
        namespace="ns",
        db_path=db_path,
    )
    assert "failed" in failed["rag_status"].lower()


@pytest.mark.asyncio
async def test_ui_service_request_clarifications_and_inspect_family_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test ui service request clarifications and inspect family branches."""

    db_path = tmp_path / "ui.sqlite3"
    service.ensure_dashboard_session("s-llm", db_path=db_path)

    async def _clarify_ok(*_a: Any, **_k: Any) -> Any:
        """Test clarify ok."""

        return service.ClarificationResponse(
            normalized_brief="normalized brief text", questions=["q1"]
        )

    monkeypatch.setattr(service, "_run_structured_agent", _clarify_ok)
    goal_text = "design goal"
    state_ok = await service.request_clarifications("s-llm", goal_text, db_path=db_path)
    assert "Generated clarifying questions" in state_ok["latest_message"]

    async def _clarify_fail(*_a: Any, **_k: Any) -> Any:
        """Test clarify fail."""

        return RecoverableFailure(
            explanation="clarify failed",
            remediation_steps=["set token"],
            retry_focus="token",
            should_retry=True,
        )

    monkeypatch.setattr(service, "_run_structured_agent", _clarify_fail)
    state_fail = await service.request_clarifications(
        "s-llm", goal_text, db_path=db_path
    )
    assert state_fail["latest_error_text"] == "clarify failed"

    async def _inspect_ok(*_a: Any, **_k: Any) -> Any:
        """Test inspect ok."""

        return service.FamilyInspection(
            family="bracket",
            confidence="high",
            evidence=["ev1"],
            warnings=["warn1"],
            checkpoints=[
                service.CheckpointCandidate(
                    title="CP1", allowed_tools=["create_sketch"], rationale="route"
                )
            ],
        )

    monkeypatch.setattr(service, "_run_structured_agent", _inspect_ok)
    inspect_ok = await service.inspect_family("s-llm", goal_text, db_path=db_path)
    assert inspect_ok["proposed_family"] == "bracket"

    async def _inspect_fail(*_a: Any, **_k: Any) -> Any:
        """Test inspect fail."""

        return RecoverableFailure(
            explanation="inspect failed",
            remediation_steps=["retry"],
            retry_focus="inspect",
            should_retry=True,
        )

    monkeypatch.setattr(service, "_run_structured_agent", _inspect_fail)
    inspect_fail = await service.inspect_family("s-llm", goal_text, db_path=db_path)
    assert inspect_fail["latest_error_text"] == "inspect failed"


@pytest.mark.asyncio
async def test_ui_service_refresh_preview_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test ui service refresh preview success and failure."""

    db_path = tmp_path / "ui.sqlite3"
    preview_dir = tmp_path / "previews"
    model_path = tmp_path / "part.sldprt"
    model_path.write_text("model", encoding="utf-8")

    service.ensure_dashboard_session("s-prev", db_path=db_path)
    service._merge_metadata(
        "s-prev", db_path=db_path, active_model_path=str(model_path)
    )

    class _PreviewAdapter:
        """Test preview adapter."""

        async def connect(self) -> None:
            """Test connect."""

            return None

        async def disconnect(self) -> None:
            """Test disconnect."""

            return None

        async def open_model(self, _path: str) -> _Result:
            """Test open model."""

            return _Result(is_success=True)

        async def export_image(self, payload: dict[str, Any]) -> _Result:
            """Test export image."""

            out = Path(str(payload["file_path"]))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"png")
            return _Result(is_success=True, data={"path": str(out)})

        async def export_file(self, out_path: str, _fmt: str) -> _Result:
            """Test export file."""

            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"stl")
            return _Result(is_success=True)

    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())

    async def _create_ok(_config: Any) -> Any:
        """Test create ok."""

        return _PreviewAdapter()

    monkeypatch.setattr(service, "create_adapter", _create_ok)
    ok = await service.refresh_preview(
        "s-prev", db_path=db_path, preview_dir=preview_dir
    )
    assert "Preview refreshed" in ok["latest_message"]

    class _NoExportAdapter:
        """Test no export adapter."""

        async def connect(self) -> None:
            # Simulate a completely broken adapter so the outer exception
            # handler fires and sets "Preview refresh failed".
            """Test connect."""

            raise RuntimeError("Adapter not available")

        async def disconnect(self) -> None:
            """Test disconnect."""

            return None

    async def _create_fail(_config: Any) -> Any:
        """Test create fail."""

        return _NoExportAdapter()

    monkeypatch.setattr(service, "create_adapter", _create_fail)
    failed = await service.refresh_preview(
        "s-prev", db_path=db_path, preview_dir=preview_dir
    )
    assert "Preview refresh failed" in failed["latest_message"]


def test_ui_service_reconcile_and_state_variants(tmp_path: Path) -> None:
    """Test ui service reconcile and state variants."""

    db_path = tmp_path / "ui.sqlite3"
    service.ensure_dashboard_session("s-rec", db_path=db_path)

    early = service.reconcile_manual_edits("s-rec", db_path=db_path)
    assert "Not enough snapshots" in early["latest_message"]

    p1 = tmp_path / "one.png"
    p1.write_bytes(b"1")
    service.insert_model_state_snapshot(
        session_id="s-rec",
        screenshot_path=str(p1),
        state_fingerprint="same",
        db_path=db_path,
    )
    service.insert_model_state_snapshot(
        session_id="s-rec",
        screenshot_path=str(p1),
        state_fingerprint="same",
        db_path=db_path,
    )
    unchanged = service.reconcile_manual_edits("s-rec", db_path=db_path)
    assert "No visual/state change" in unchanged["latest_message"]

    row = service.get_design_session("s-rec", db_path=db_path)
    assert row is not None
    metadata = json.loads(row["metadata_json"])
    metadata["active_model_path"] = "C:/tmp/part.sldprt"
    metadata["preview_stl_ready"] = True
    service.upsert_design_session(
        session_id="s-rec",
        user_goal=row["user_goal"],
        source_mode=row["source_mode"],
        accepted_family=row["accepted_family"],
        status=row["status"],
        current_checkpoint_index=row["current_checkpoint_index"],
        metadata_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    state = service.build_dashboard_state("s-rec", db_path=db_path)
    assert "api/ui/viewer" in state["preview_viewer_url"]
