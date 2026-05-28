"""Tests for ui.services._utils helpers."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

from solidworks_mcp.ui.services import _utils


def test_feature_target_status_invalid_targets() -> None:
    """Invalid feature target text should return a guidance message."""
    # Provide non-empty text that yields no normalized targets.
    status, matched, missing = _utils.feature_target_status([], "not-a-target")
    assert "No valid feature targets found" in status
    assert matched == []
    assert missing == []


def test_read_reference_file_pdf_uses_reader(monkeypatch, tmp_path) -> None:
    """PDF files should be parsed with PdfReader when available."""
    # Provide a fake PdfReader to cover the PDF branch.
    class _Page:
        def extract_text(self):
            return "page text"

    class _Reader:
        def __init__(self, _path):
            self.pages = [_Page(), _Page()]

    monkeypatch.setattr(_utils, "import_module", lambda _name: SimpleNamespace(PdfReader=_Reader))
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"pdf")

    text = _utils.read_reference_file(pdf_path)
    assert text == "page text\n\npage text"


def test_read_reference_url_pdf_requires_pypdf(monkeypatch) -> None:
    """PDF URLs should raise when PdfReader is missing."""
    # Simulate a PDF response with no pypdf installed.
    monkeypatch.setattr(_utils, "import_module", lambda _name: (_ for _ in ()).throw(ImportError("nope")))

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
    monkeypatch.setattr(_utils, "import_module", lambda _name: SimpleNamespace(PdfReader=None))

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


def test_read_reference_url_plain_text(monkeypatch) -> None:
    """Plain text responses should decode without HTML parsing."""
    # Return a text/plain response and assert the decoded string.
    monkeypatch.setattr(_utils, "import_module", lambda _name: SimpleNamespace(PdfReader=None))

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
