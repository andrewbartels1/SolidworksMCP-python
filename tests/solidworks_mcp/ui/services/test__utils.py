"""Tests for ui.services._utils helpers."""

from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from solidworks_mcp.ui.services import _utils


def test_feature_target_status_invalid_targets() -> None:
    """Path-like feature text should return a guidance message with no results."""
    # A Windows-path token is filtered out by normalize_feature_targets, yielding
    # an empty requested list while feature_target_text is still non-empty →
    # the "No valid feature targets found" branch fires.
    status, matched, missing = _utils.feature_target_status(
        [], r"C:\Users\model.sldprt"
    )
    assert "No valid feature targets found" in status
    assert matched == []
    assert missing == []


def test_feature_target_status_no_match_returns_missing() -> None:
    """A valid token with no matching features should land in missing."""
    # "BossExtrude1" is a valid feature token but features list is empty.
    status, matched, missing = _utils.feature_target_status([], "BossExtrude1")
    assert "No matching feature targets found" in status
    assert matched == []
    assert missing == ["BossExtrude1"]


def test_read_reference_source_pdf_uses_reader(monkeypatch, tmp_path) -> None:
    """PDF files should be parsed with PdfReader when available."""

    # Provide a fake PdfReader to cover the PDF branch.
    class _Page:
        def extract_text(self):
            return "page text"

    class _Reader:
        def __init__(self, _path):
            self.pages = [_Page(), _Page()]

    monkeypatch.setattr(
        _utils, "import_module", lambda _name: SimpleNamespace(PdfReader=_Reader)
    )
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"pdf")

    text = _utils.read_reference_source(pdf_path)
    assert text == "page text\n\npage text"


def test_read_reference_url_pdf_requires_pypdf(monkeypatch) -> None:
    """PDF URLs should raise when PdfReader is missing."""
    # Simulate a PDF response with no pypdf installed.
    monkeypatch.setattr(
        _utils,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("nope")),
    )

    class _Headers:
        @staticmethod
        def get_content_type():
            return "application/pdf"

        @staticmethod
        def get_content_charset():
            return "utf-8"

    class _Response:
        headers = _Headers()

        def read(self):
            return b"%PDF-1.4"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(_utils, "urlopen", lambda *_a, **_kw: _Response())

    with pytest.raises(RuntimeError, match="Install pypdf"):
        _utils.read_reference_url("http://example.com/doc.pdf")


def test_read_reference_url_html_parses_text(monkeypatch) -> None:
    """HTML responses should be stripped to text."""
    # Provide a basic HTML response and assert text extraction.
    monkeypatch.setattr(
        _utils, "import_module", lambda _name: SimpleNamespace(PdfReader=None)
    )

    class _Headers:
        @staticmethod
        def get_content_type():
            return "text/html"

        @staticmethod
        def get_content_charset():
            return "utf-8"

    class _Response:
        headers = _Headers()

        def read(self):
            return b"<html><body><p>Hello</p></body></html>"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(_utils, "urlopen", lambda *_a, **_kw: _Response())

    text, label = _utils.read_reference_url("http://example.com/doc.html")
    assert text == "Hello"
    assert label == "doc.html"


def test_read_reference_url_pdf_with_reader_success(monkeypatch) -> None:
    """PDF URLs with PdfReader available should extract text from pages (lines 892-894)."""

    # Provide a real PdfReader stub and a PDF response → text extraction path.
    class _Page:
        def extract_text(self):
            return "pdf page content"

    class _Reader:
        def __init__(self, _bytes):
            self.pages = [_Page()]

    monkeypatch.setattr(
        _utils, "import_module", lambda _name: SimpleNamespace(PdfReader=_Reader)
    )

    class _Headers:
        @staticmethod
        def get_content_type():
            return "application/pdf"

        @staticmethod
        def get_content_charset():
            return "utf-8"

    class _Response:
        headers = _Headers()

        def read(self):
            return b"%PDF-1.4"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(_utils, "urlopen", lambda *_a, **_kw: _Response())

    text, label = _utils.read_reference_url("http://example.com/doc.pdf")
    assert text == "pdf page content"
    assert label == "doc.pdf"


def test_read_reference_url_plain_text(monkeypatch) -> None:
    """Plain text responses should decode without HTML parsing."""
    # Return a text/plain response and assert the decoded string.
    monkeypatch.setattr(
        _utils, "import_module", lambda _name: SimpleNamespace(PdfReader=None)
    )

    class _Headers:
        @staticmethod
        def get_content_type():
            return "text/plain"

        @staticmethod
        def get_content_charset():
            return "utf-8"

    class _Response:
        headers = _Headers()

        def read(self):
            return b"plain text"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(_utils, "urlopen", lambda *_a, **_kw: _Response())

    text, label = _utils.read_reference_url("http://example.com/readme.txt")
    assert text == "plain text"
    assert label == "readme.txt"


# ---------------------------------------------------------------------------
# parse_json_blob
# ---------------------------------------------------------------------------


def test_parse_json_blob_none_returns_empty() -> None:
    assert _utils.parse_json_blob(None) == {}


def test_parse_json_blob_invalid_json_returns_empty() -> None:
    assert _utils.parse_json_blob("{not-valid") == {}


def test_parse_json_blob_list_returns_empty() -> None:
    assert _utils.parse_json_blob('["a", "b"]') == {}


def test_parse_json_blob_valid_dict() -> None:
    assert _utils.parse_json_blob('{"key": 1}') == {"key": 1}


def test_parse_json_blob_empty_string_returns_empty() -> None:
    assert _utils.parse_json_blob("") == {}


# ---------------------------------------------------------------------------
# sanitize_ui_text
# ---------------------------------------------------------------------------


def test_sanitize_ui_text_none_returns_fallback() -> None:
    assert _utils.sanitize_ui_text(None, "default") == "default"


def test_sanitize_ui_text_empty_returns_fallback() -> None:
    assert _utils.sanitize_ui_text("   ", "fallback") == "fallback"


def test_sanitize_ui_text_bare_quote_returns_fallback() -> None:
    assert _utils.sanitize_ui_text('"', "fb") == "fb"
    assert _utils.sanitize_ui_text("'", "fb") == "fb"


def test_sanitize_ui_text_template_placeholder_returns_fallback() -> None:
    assert _utils.sanitize_ui_text("{{ field }}", "fb") == "fb"


def test_sanitize_ui_text_pydantic_expression_returns_fallback() -> None:
    assert _utils.sanitize_ui_text("$result.value", "fb") == "fb"
    assert _utils.sanitize_ui_text("$error", "fb") == "fb"


def test_sanitize_ui_text_valid_value_returned() -> None:
    assert _utils.sanitize_ui_text("hello", "fb") == "hello"


# ---------------------------------------------------------------------------
# sanitize_model_path_text
# ---------------------------------------------------------------------------


def test_sanitize_model_path_text_strips_double_quotes() -> None:
    assert _utils.sanitize_model_path_text('"C:/model.sldprt"') == "C:/model.sldprt"


def test_sanitize_model_path_text_strips_single_quotes() -> None:
    assert _utils.sanitize_model_path_text("'C:/model.sldprt'") == "C:/model.sldprt"


def test_sanitize_model_path_text_returns_plain_path() -> None:
    assert _utils.sanitize_model_path_text("C:/model.sldprt") == "C:/model.sldprt"


def test_sanitize_model_path_text_empty() -> None:
    assert _utils.sanitize_model_path_text(None) == ""


# ---------------------------------------------------------------------------
# sanitize_preview_viewer_url
# ---------------------------------------------------------------------------


def test_sanitize_preview_viewer_url_valid() -> None:
    url = "http://127.0.0.1:8766/api/ui/viewer/s1"
    result = _utils.sanitize_preview_viewer_url(
        url, session_id="s1", api_origin="http://127.0.0.1:8766"
    )
    assert result == url


def test_sanitize_preview_viewer_url_wrong_path_returns_empty() -> None:
    url = "http://127.0.0.1:8766/wrong/path"
    result = _utils.sanitize_preview_viewer_url(
        url, session_id="s1", api_origin="http://127.0.0.1:8766"
    )
    assert result == ""


def test_sanitize_preview_viewer_url_wrong_netloc_returns_empty() -> None:
    url = "http://evil.com/api/ui/viewer/s1"
    result = _utils.sanitize_preview_viewer_url(
        url, session_id="s1", api_origin="http://127.0.0.1:8766"
    )
    assert result == ""


def test_sanitize_preview_viewer_url_empty_value_returns_empty() -> None:
    result = _utils.sanitize_preview_viewer_url(
        None, session_id="s1", api_origin="http://127.0.0.1:8766"
    )
    assert result == ""


def test_sanitize_preview_viewer_url_no_scheme_passes_path_check() -> None:
    """URL without scheme/netloc should pass if path matches."""
    url = "/api/ui/viewer/s1"
    result = _utils.sanitize_preview_viewer_url(
        url, session_id="s1", api_origin="http://127.0.0.1:8766"
    )
    # No netloc means the netloc check is skipped
    assert result == url


# ---------------------------------------------------------------------------
# trace helpers
# ---------------------------------------------------------------------------


def test_trace_json_returns_pretty_json() -> None:
    result = _utils.trace_json({"key": "value"})
    assert '"key"' in result
    assert '"value"' in result


def test_trace_json_handles_non_serializable() -> None:
    class _Custom:
        def __repr__(self):
            return "custom"

    result = _utils.trace_json({"obj": _Custom()})
    assert "custom" in result


def test_trace_session_row_removes_metadata_json() -> None:
    row = {"id": 1, "metadata_json": '{"big": "data"}', "user_goal": "test"}
    result = _utils.trace_session_row(row)
    assert "metadata_json" not in result
    assert result["user_goal"] == "test"


def test_trace_session_row_returns_empty_for_none() -> None:
    assert _utils.trace_session_row(None) == {}


def test_trace_tool_records_returns_last_ten() -> None:
    records = [{"id": i, "tool_name": f"tool_{i}", "success": True,
                "input_json": None, "output_json": None, "created_at": None}
               for i in range(15)]
    result = _utils.trace_tool_records(records)
    assert len(result) == 10
    assert result[0]["id"] == 5  # last 10 of 15


def test_trace_tool_records_returns_all_when_fewer_than_ten() -> None:
    records = [{"id": i, "tool_name": f"t{i}", "success": True,
                "input_json": None, "output_json": None, "created_at": None}
               for i in range(3)]
    result = _utils.trace_tool_records(records)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# safe_context_name
# ---------------------------------------------------------------------------


def test_safe_context_name_alphanumeric_only() -> None:
    assert _utils.safe_context_name("my-context_1", "sess") == "my-context_1"


def test_safe_context_name_special_chars_replaced() -> None:
    result = _utils.safe_context_name("hello world!", "s")
    assert " " not in result
    assert "!" not in result


def test_safe_context_name_none_falls_back_to_session_id() -> None:
    result = _utils.safe_context_name(None, "my-session")
    assert result == "my-session"


def test_safe_context_name_empty_falls_back_to_default() -> None:
    result = _utils.safe_context_name("", "")
    assert result == "prefab-dashboard"


# ---------------------------------------------------------------------------
# normalize_workflow_mode
# ---------------------------------------------------------------------------


def test_normalize_workflow_mode_edit_existing() -> None:
    assert _utils.normalize_workflow_mode("edit_existing") == "edit_existing"


def test_normalize_workflow_mode_new_design() -> None:
    assert _utils.normalize_workflow_mode("new_design") == "new_design"


def test_normalize_workflow_mode_unknown_returns_default() -> None:
    assert _utils.normalize_workflow_mode("bad_mode") == _utils.DEFAULT_WORKFLOW_MODE


def test_normalize_workflow_mode_none_returns_default() -> None:
    assert _utils.normalize_workflow_mode(None) == _utils.DEFAULT_WORKFLOW_MODE


# ---------------------------------------------------------------------------
# workflow_copy
# ---------------------------------------------------------------------------


def test_workflow_copy_edit_existing() -> None:
    label, guidance, header = _utils.workflow_copy("edit_existing")
    assert "Editing" in label
    assert "Attach" in header


def test_workflow_copy_new_design() -> None:
    label, guidance, header = _utils.workflow_copy("new_design")
    assert "New Design" in label
    assert "Define Goal" in header


def test_workflow_copy_unselected_with_active_model() -> None:
    label, guidance, header = _utils.workflow_copy("unselected", "C:/model.sldprt")
    assert "Choose" in label
    assert "already attached" in guidance


def test_workflow_copy_unselected_no_model() -> None:
    label, guidance, header = _utils.workflow_copy("unselected", None)
    assert "Choose" in label
    assert "existing SolidWorks" in guidance


# ---------------------------------------------------------------------------
# provider_from_model_name
# ---------------------------------------------------------------------------


def test_provider_from_model_name_github() -> None:
    assert _utils.provider_from_model_name("github:openai/gpt-4.1") == "github"


def test_provider_from_model_name_openai() -> None:
    assert _utils.provider_from_model_name("openai:gpt-4.1") == "openai"


def test_provider_from_model_name_anthropic() -> None:
    assert _utils.provider_from_model_name("anthropic:claude-3") == "anthropic"


def test_provider_from_model_name_local() -> None:
    assert _utils.provider_from_model_name("local:gemma4:e2b") == "local"


def test_provider_from_model_name_custom() -> None:
    assert _utils.provider_from_model_name("unknown-model") == "custom"


# ---------------------------------------------------------------------------
# default_model_for_profile
# ---------------------------------------------------------------------------


def test_default_model_for_profile_local_small() -> None:
    result = _utils.default_model_for_profile("local", "small")
    assert result.startswith("local:")


def test_default_model_for_profile_local_large() -> None:
    result = _utils.default_model_for_profile("local", "large")
    assert "26b" in result


def test_default_model_for_profile_github_balanced() -> None:
    result = _utils.default_model_for_profile("github", "balanced")
    assert result.startswith("github:")


def test_default_model_for_profile_unknown_profile_defaults_to_balanced() -> None:
    result = _utils.default_model_for_profile("local", "unknown")
    assert result == _utils.default_model_for_profile("local", "balanced")


# ---------------------------------------------------------------------------
# normalize_model_name_for_provider
# ---------------------------------------------------------------------------


def test_normalize_model_name_already_qualified() -> None:
    result = _utils.normalize_model_name_for_provider(
        "github:openai/gpt-4.1", provider="github"
    )
    assert result == "github:openai/gpt-4.1"


def test_normalize_model_name_empty_uses_profile_default() -> None:
    result = _utils.normalize_model_name_for_provider(
        None, provider="local", profile="small"
    )
    assert result.startswith("local:")


def test_normalize_model_name_github_without_slash_gets_prefix() -> None:
    result = _utils.normalize_model_name_for_provider(
        "gpt-4.1", provider="github"
    )
    assert result.startswith("github:openai/")


def test_normalize_model_name_github_with_slash_passes_through() -> None:
    result = _utils.normalize_model_name_for_provider(
        "openai/gpt-4.1", provider="github"
    )
    assert result == "github:openai/gpt-4.1"


def test_normalize_model_name_openai_provider() -> None:
    result = _utils.normalize_model_name_for_provider(
        "gpt-4o", provider="openai"
    )
    assert result == "openai:gpt-4o"


def test_normalize_model_name_anthropic_provider() -> None:
    result = _utils.normalize_model_name_for_provider(
        "claude-3", provider="anthropic"
    )
    assert result == "anthropic:claude-3"


def test_normalize_model_name_unknown_provider_returns_raw() -> None:
    result = _utils.normalize_model_name_for_provider(
        "mymodel", provider="custom"
    )
    assert result == "mymodel"


def test_normalize_model_name_local_provider() -> None:
    # Unqualified name (no colon) → should get "local:" prefix
    result = _utils.normalize_model_name_for_provider("gemma4", provider="local")
    assert result == "local:gemma4"


def test_normalize_model_name_local_provider_ollama_tag_passthrough() -> None:
    # "gemma4:e2b" contains ":" so the function treats it as already-qualified
    # and returns it unchanged regardless of the provider argument.
    result = _utils.normalize_model_name_for_provider("gemma4:e2b", provider="local")
    assert result == "gemma4:e2b"


# ---------------------------------------------------------------------------
# provider_has_credentials
# ---------------------------------------------------------------------------


def test_provider_has_credentials_github_with_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_API_KEY", "tok123")
    assert _utils.provider_has_credentials("github:openai/gpt-4.1") is True


def test_provider_has_credentials_github_gh_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    monkeypatch.setenv("GH_TOKEN", "ghtoken")
    assert _utils.provider_has_credentials("github:openai/gpt-4.1") is True


def test_provider_has_credentials_github_no_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert _utils.provider_has_credentials("github:openai/gpt-4.1") is False


def test_provider_has_credentials_openai(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-xxx")
    assert _utils.provider_has_credentials("openai:gpt-4.1") is True


def test_provider_has_credentials_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    assert _utils.provider_has_credentials("anthropic:claude-3") is True


def test_provider_has_credentials_local_needs_endpoint() -> None:
    assert _utils.provider_has_credentials("local:gemma4:e2b", "http://localhost:11434") is True
    assert _utils.provider_has_credentials("local:gemma4:e2b", None) is False


def test_provider_has_credentials_custom_always_true() -> None:
    assert _utils.provider_has_credentials("unknown-model") is True


# ---------------------------------------------------------------------------
# normalize_feature_targets
# ---------------------------------------------------------------------------


def test_normalize_feature_targets_at_prefix_stripped() -> None:
    result = _utils.normalize_feature_targets("@Boss-Extrude1, @Sketch2")
    assert "Boss-Extrude1" in result
    assert "Sketch2" in result


def test_normalize_feature_targets_newline_separated() -> None:
    result = _utils.normalize_feature_targets("@Feat1\n@Feat2")
    assert "Feat1" in result
    assert "Feat2" in result


def test_normalize_feature_targets_path_tokens_filtered() -> None:
    result = _utils.normalize_feature_targets(r"C:\Users\model.sldprt, Boss-Extrude1")
    assert "Boss-Extrude1" in result
    assert not any("C:" in t for t in result)


def test_normalize_feature_targets_empty_returns_empty() -> None:
    assert _utils.normalize_feature_targets(None) == []
    assert _utils.normalize_feature_targets("") == []


# ---------------------------------------------------------------------------
# _looks_like_path_token
# ---------------------------------------------------------------------------


def test_looks_like_path_token_windows_drive() -> None:
    assert _utils._looks_like_path_token("C:\\Users\\model.sldprt") is True


def test_looks_like_path_token_forward_slash() -> None:
    assert _utils._looks_like_path_token("/home/user/part.sldprt") is True


def test_looks_like_path_token_extension() -> None:
    assert _utils._looks_like_path_token("model.step") is True
    assert _utils._looks_like_path_token("part.sldprt") is True


def test_looks_like_path_token_feature_name_false() -> None:
    assert _utils._looks_like_path_token("Boss-Extrude1") is False


def test_looks_like_path_token_empty_false() -> None:
    assert _utils._looks_like_path_token("") is False


# ---------------------------------------------------------------------------
# feature_target_status — additional branches
# ---------------------------------------------------------------------------


def test_feature_target_status_no_input() -> None:
    status, matched, missing = _utils.feature_target_status([], None)
    assert "No grounded" in status
    assert matched == []
    assert missing == []


def test_feature_target_status_partial_match() -> None:
    features = [{"name": "Boss-Extrude1"}, {"name": "Sketch1"}]
    status, matched, missing = _utils.feature_target_status(
        features, "Boss-Extrude1, MissingFeature"
    )
    assert "Partially grounded" in status
    assert "Boss-Extrude1" in matched
    assert "MissingFeature" in missing


def test_feature_target_status_all_matched() -> None:
    features = [{"name": "Boss-Extrude1"}, {"name": "Sketch1"}]
    status, matched, missing = _utils.feature_target_status(
        features, "@Boss-Extrude1, @Sketch1"
    )
    assert "Grounded feature target" in status
    assert missing == []
    assert len(matched) == 2


# ---------------------------------------------------------------------------
# feature_grounding_warning_text
# ---------------------------------------------------------------------------


def test_feature_grounding_warning_no_model() -> None:
    result = _utils.feature_grounding_warning_text(
        active_model_path="",
        feature_target_text="@Feat1",
        feature_tree_count=0,
    )
    assert result == ""


def test_feature_grounding_warning_no_feature_text() -> None:
    result = _utils.feature_grounding_warning_text(
        active_model_path="C:/model.sldprt",
        feature_target_text="",
        feature_tree_count=0,
    )
    assert result == ""


def test_feature_grounding_warning_with_tree() -> None:
    result = _utils.feature_grounding_warning_text(
        active_model_path="C:/model.sldprt",
        feature_target_text="@Feat1",
        feature_tree_count=5,
    )
    assert result == ""


def test_feature_grounding_warning_no_tree() -> None:
    result = _utils.feature_grounding_warning_text(
        active_model_path="C:/model.sldprt",
        feature_target_text="@Feat1",
        feature_tree_count=0,
    )
    assert "unavailable" in result


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def test_ensure_preview_dir_creates_directory(tmp_path: Path) -> None:
    preview_dir = tmp_path / "previews"
    result = _utils.ensure_preview_dir(preview_dir)
    assert result.exists()
    assert result == preview_dir


def test_ensure_uploaded_model_dir_creates_directory(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    result = _utils.ensure_uploaded_model_dir(upload_dir)
    assert result.exists()


def test_ensure_context_dir_creates_directory(tmp_path: Path) -> None:
    context_dir = tmp_path / "context"
    result = _utils.ensure_context_dir(context_dir)
    assert result.exists()


def test_context_file_path_returns_json(tmp_path: Path) -> None:
    result = _utils.context_file_path("sess1", context_dir=tmp_path)
    assert result.suffix == ".json"
    assert "sess1" in str(result)


def test_context_file_path_with_context_name(tmp_path: Path) -> None:
    result = _utils.context_file_path(
        "sess1", context_name="my-context", context_dir=tmp_path
    )
    assert "my-context" in result.name


# ---------------------------------------------------------------------------
# HTMLTextExtractor
# ---------------------------------------------------------------------------


def test_html_text_extractor_basic() -> None:
    from solidworks_mcp.ui.services._utils import HTMLTextExtractor
    parser = HTMLTextExtractor()
    parser.feed("<html><body><p>Hello World</p></body></html>")
    assert "Hello World" in parser.text()


def test_html_text_extractor_skips_script_content() -> None:
    from solidworks_mcp.ui.services._utils import HTMLTextExtractor
    parser = HTMLTextExtractor()
    parser.feed("<html><body><script>alert('skip')</script><p>Keep</p></body></html>")
    assert "Keep" in parser.text()
    assert "alert" not in parser.text()


def test_html_text_extractor_handles_nested_skip_tags() -> None:
    from solidworks_mcp.ui.services._utils import HTMLTextExtractor
    parser = HTMLTextExtractor()
    parser.feed("<nav><script>js</script></nav><p>Visible</p>")
    assert "Visible" in parser.text()
    assert "js" not in parser.text()


# ---------------------------------------------------------------------------
# filter_docs_text
# ---------------------------------------------------------------------------


def test_filter_docs_text_returns_relevant_lines() -> None:
    text = "Line about extrude.\nLine about sketch.\nOther content."
    result = _utils.filter_docs_text(text, "extrude sketch")
    assert "extrude" in result or "sketch" in result


def test_filter_docs_text_empty_text_returns_empty() -> None:
    assert _utils.filter_docs_text("", "extrude") == ""


def test_filter_docs_text_respects_max_chars() -> None:
    text = "x" * 10000
    result = _utils.filter_docs_text(text, "x", max_chars=100)
    assert len(result) <= 100


# ---------------------------------------------------------------------------
# is_url_reference
# ---------------------------------------------------------------------------


def test_is_url_reference_http() -> None:
    assert _utils.is_url_reference("http://example.com/guide.pdf") is True


def test_is_url_reference_https() -> None:
    assert _utils.is_url_reference("https://example.com/guide.html") is True


def test_is_url_reference_local_path() -> None:
    assert _utils.is_url_reference("/local/path/file.md") is False


def test_is_url_reference_empty() -> None:
    assert _utils.is_url_reference("") is False


# ---------------------------------------------------------------------------
# read_reference_source
# ---------------------------------------------------------------------------


def test_read_reference_source_text_file(tmp_path: Path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# Guide\nThis is a guide.", encoding="utf-8")
    result = _utils.read_reference_source(source)
    assert "# Guide" in result


def test_read_reference_source_pdf_no_pypdf_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        _utils, "import_module", lambda _name: (_ for _ in ()).throw(ImportError())
    )
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"PDF content")
    with pytest.raises(RuntimeError, match="Install pypdf"):
        _utils.read_reference_source(pdf_path)


# ---------------------------------------------------------------------------
# materialize_uploaded_model
# ---------------------------------------------------------------------------


def test_materialize_uploaded_model_no_files_raises() -> None:
    with pytest.raises(RuntimeError, match="No uploaded model file"):
        _utils.materialize_uploaded_model("sess1", [])


def test_materialize_uploaded_model_missing_name_raises() -> None:
    with pytest.raises(RuntimeError, match="missing a filename"):
        _utils.materialize_uploaded_model("sess1", [{"name": "", "data": "aaa"}])


def test_materialize_uploaded_model_bad_suffix_raises() -> None:
    with pytest.raises(RuntimeError, match="Unsupported uploaded model type"):
        _utils.materialize_uploaded_model("sess1", [{"name": "file.txt", "data": "aaa"}])


def test_materialize_uploaded_model_missing_data_raises() -> None:
    with pytest.raises(RuntimeError, match="missing file data"):
        _utils.materialize_uploaded_model("sess1", [{"name": "part.sldprt"}])


def test_materialize_uploaded_model_bad_base64_raises() -> None:
    with pytest.raises(RuntimeError, match="not valid base64"):
        _utils.materialize_uploaded_model(
            "sess1", [{"name": "part.sldprt", "data": "not-valid-base64!!!"}]
        )


def test_materialize_uploaded_model_success(tmp_path: Path) -> None:
    data = base64.b64encode(b"solidworks binary data").decode("ascii")
    result = _utils.materialize_uploaded_model(
        "sess1",
        [{"name": "part.sldprt", "data": data}],
        upload_dir=tmp_path,
    )
    assert result.exists()
    assert result.name == "part.sldprt"
    assert result.read_bytes() == b"solidworks binary data"


# ---------------------------------------------------------------------------
# merge_metadata and persist_ui_action (database-backed)
# ---------------------------------------------------------------------------


def test_merge_metadata_creates_and_updates(tmp_path: Path) -> None:
    """merge_metadata should create a session and merge key-value pairs."""
    db_path = tmp_path / "test.sqlite3"
    # First call - creates session
    result = _utils.merge_metadata("test-session", db_path=db_path, key1="value1")
    assert result.get("key1") == "value1"

    # Second call - merges additional keys
    result2 = _utils.merge_metadata(
        "test-session", db_path=db_path, key2="value2"
    )
    assert result2.get("key1") == "value1"
    assert result2.get("key2") == "value2"


def test_merge_metadata_with_user_goal(tmp_path: Path) -> None:
    """merge_metadata with user_goal should update the session's user_goal column."""
    db_path = tmp_path / "test.sqlite3"
    result = _utils.merge_metadata(
        "goal-session",
        db_path=db_path,
        user_goal="Build a bracket",
        extra_key="extra_value",
    )
    assert result.get("extra_key") == "extra_value"


def test_persist_ui_action_with_metadata_updates(tmp_path: Path) -> None:
    """persist_ui_action should merge metadata and insert a tool call record."""
    db_path = tmp_path / "test.sqlite3"
    result = _utils.persist_ui_action(
        "action-session",
        tool_name="ui.test",
        db_path=db_path,
        metadata_updates={"status": "testing"},
        input_payload={"arg": "value"},
        output_payload={"result": "done"},
    )
    assert result.get("status") == "testing"


def test_persist_ui_action_output_metadata_flag(tmp_path: Path) -> None:
    """When output_metadata=True, the merged metadata is used as output_json."""
    db_path = tmp_path / "test.sqlite3"
    result = _utils.persist_ui_action(
        "meta-out-session",
        tool_name="ui.meta_output",
        db_path=db_path,
        metadata_updates={"my_key": "my_value"},
        output_metadata=True,
    )
    assert result.get("my_key") == "my_value"


def test_persist_ui_action_no_metadata_updates(tmp_path: Path) -> None:
    """persist_ui_action without metadata_updates should still insert a tool call record."""
    db_path = tmp_path / "test.sqlite3"
    result = _utils.persist_ui_action(
        "no-meta-session",
        tool_name="ui.no_meta",
        db_path=db_path,
        success=False,
    )
    # Returns empty merged_metadata (no updates)
    assert result == {}
