from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.solidworks_mcp.agents.schemas import RecoverableFailure
from src.solidworks_mcp.ui import service


class _DummyResult:
    def __init__(
        self, is_success: bool = True, data: Any = None, error: str | None = None
    ):
        self.is_success = is_success
        self.data = data
        self.error = error


class _DummyAdapter:
    def __init__(
        self, fail_tool: str | None = None, with_cut_extrude: bool = False
    ) -> None:
        self.fail_tool = fail_tool
        self.connected = False
        self.with_cut_extrude = with_cut_extrude

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def create_sketch(self, _plane: str) -> _DummyResult:
        return _DummyResult(is_success=self.fail_tool != "create_sketch", error="boom")

    async def add_line(self, *_args: Any) -> _DummyResult:
        return _DummyResult(is_success=self.fail_tool != "add_line", error="boom")

    async def create_extrusion(self, _params: Any) -> _DummyResult:
        return _DummyResult(
            is_success=self.fail_tool != "create_extrusion", error="boom"
        )

    async def create_cut(self, _sketch: str, _depth: float) -> _DummyResult:
        return _DummyResult(is_success=self.fail_tool != "create_cut", error="boom")

    async def create_cut_extrude(self, _params: Any) -> _DummyResult:
        return _DummyResult(is_success=self.fail_tool != "create_cut", error="boom")


class _Headers:
    def __init__(self, content_type: str, charset: str = "utf-8") -> None:
        self._content_type = content_type
        self._charset = charset

    def get_content_type(self) -> str:
        return self._content_type

    def get_content_charset(self) -> str:
        return self._charset


class _Response:
    def __init__(self, body: bytes, content_type: str, charset: str = "utf-8") -> None:
        self._body = body
        self.headers = _Headers(content_type, charset)

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_materialize_uploaded_model_validation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "DEFAULT_UPLOADED_MODEL_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="No uploaded model"):
        service._materialize_uploaded_model("s", None)

    with pytest.raises(RuntimeError, match="missing a filename"):
        service._materialize_uploaded_model("s", [{"name": "", "data": "x"}])

    with pytest.raises(RuntimeError, match="Unsupported uploaded model type"):
        service._materialize_uploaded_model("s", [{"name": "bad.txt", "data": "x"}])

    with pytest.raises(RuntimeError, match="missing file data"):
        service._materialize_uploaded_model("s", [{"name": "ok.sldprt", "data": ""}])

    with pytest.raises(RuntimeError, match="not valid base64"):
        service._materialize_uploaded_model("s", [{"name": "ok.sldprt", "data": "%%%"}])


def test_materialize_uploaded_model_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "DEFAULT_UPLOADED_MODEL_DIR", tmp_path)
    encoded = base64.b64encode(b"solidworks").decode("ascii")

    out = service._materialize_uploaded_model(
        "session-1", [{"name": "part.sldprt", "data": encoded}]
    )

    assert out.exists()
    assert out.read_bytes() == b"solidworks"


def test_read_reference_url_html_and_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (
        b"<html><body><h1>Guide</h1><script>ignore</script><p>Step 1</p></body></html>"
    )

    monkeypatch.setattr(
        service,
        "urlopen",
        lambda request, timeout=20: _Response(html, "text/html"),
    )
    text, label = service._read_reference_url("https://example.com/guide.html")
    assert "Guide" in text
    assert "Step 1" in text
    assert "ignore" not in text
    assert label == "guide.html"

    monkeypatch.setattr(
        service,
        "urlopen",
        lambda request, timeout=20: _Response(b"abc", "text/plain"),
    )
    text2, label2 = service._read_reference_url("https://example.com/file.txt")
    assert text2 == "abc"
    assert label2 == "file.txt"


def test_read_reference_url_pdf_requires_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "urlopen",
        lambda request, timeout=20: _Response(b"%PDF", "application/pdf"),
    )
    monkeypatch.setattr(service, "PdfReader", None)

    with pytest.raises(RuntimeError, match="Install pypdf"):
        service._read_reference_url("https://example.com/file.pdf")


def test_read_reference_source_pdf_requires_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "guide.pdf"
    src.write_bytes(b"%PDF")
    monkeypatch.setattr(service, "PdfReader", None)

    with pytest.raises(RuntimeError, match="Install pypdf"):
        service._read_reference_source(src)


def test_provider_credentials_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", raising=False)

    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="tok\n"),
    )
    service._ensure_provider_credentials("github:openai/gpt-4.1")
    assert service.os.getenv("GITHUB_API_KEY") == "tok"

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        service._ensure_provider_credentials("openai:gpt-4.1")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        service._ensure_provider_credentials("anthropic:claude")

    with pytest.raises(RuntimeError, match="SOLIDWORKS_UI_LOCAL_ENDPOINT"):
        service._ensure_provider_credentials("local:foo")


def test_build_agent_model_local_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "OpenAIChatModel", None)
    monkeypatch.setattr(service, "OpenAIProvider", None)

    with pytest.raises(RuntimeError, match="provider support is not installed"):
        service._build_agent_model("local:my-model")

    assert (
        service._build_agent_model("github:openai/gpt-4.1") == "github:openai/gpt-4.1"
    )


@pytest.mark.asyncio
async def test_run_structured_agent_handles_missing_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "Agent", None)

    result = await service._run_structured_agent(
        system_prompt="s",
        user_prompt="u",
        result_type=service.ClarificationResponse,
    )

    assert isinstance(result, RecoverableFailure)


@pytest.mark.asyncio
async def test_run_checkpoint_tools_success_and_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _create_adapter(_config):
        return _DummyAdapter(with_cut_extrude=False)

    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "create_adapter", _create_adapter)

    summary = await service._run_checkpoint_tools(
        {
            "tools": [
                "create_sketch",
                "add_line",
                "create_extrusion",
                "create_cut",
                "check_interference",
                "unknown_tool",
            ]
        }
    )

    assert any(item["status"] == "success" for item in summary["tool_runs"])
    assert "check_interference" in summary["mocked_tools"]
    assert "unknown_tool" in summary["mocked_tools"]
    assert summary["failed_tools"] == []


@pytest.mark.asyncio
async def test_run_checkpoint_tools_failure_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingAdapter(_DummyAdapter):
        async def connect(self) -> None:
            raise RuntimeError("connect failed")

    async def _create_adapter(_config):
        return _FailingAdapter()

    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "create_adapter", _create_adapter)

    summary = await service._run_checkpoint_tools({"tools": ["create_sketch"]})

    assert "checkpoint.execute" in summary["failed_tools"]
    assert any(item["tool"] == "checkpoint.execute" for item in summary["tool_runs"])
