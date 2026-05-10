"""Coverage tests for src/solidworks_mcp/agents/vector_rag.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("faiss")

import src.solidworks_mcp.agents.vector_rag as vector_rag_mod
from src.solidworks_mcp.agents.vector_rag import (
    VectorRAGIndex,
    _chunk_text,
    _get_embedding_model,
    _require_faiss,
    _require_sentence_transformers,
    build_solidworks_api_docs_index,
    query_design_knowledge,
    query_solidworks_api_docs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_model(dim: int = 16) -> MagicMock:
    """Return a mock that behaves like SentenceTransformer.encode."""
    model = MagicMock()
    model.encode.side_effect = lambda texts, **kw: np.random.randn(
        len(texts), dim
    ).astype("float32")
    return model


# ---------------------------------------------------------------------------
# _require_faiss / _require_sentence_transformers
# ---------------------------------------------------------------------------


def test_require_faiss_success() -> None:
    """_require_faiss returns the faiss module when installed."""
    faiss = _require_faiss()
    assert hasattr(faiss, "IndexFlatIP")


def test_require_faiss_import_error() -> None:
    """_require_faiss raises ImportError if faiss is missing."""
    with patch.dict(sys.modules, {"faiss": None}):
        with pytest.raises(ImportError, match="faiss-cpu"):
            _require_faiss()


def test_require_sentence_transformers_success() -> None:
    """_require_sentence_transformers returns the SentenceTransformer class."""
    cls = _require_sentence_transformers()
    assert callable(cls)


def test_require_sentence_transformers_import_error() -> None:
    """_require_sentence_transformers raises ImportError if missing."""
    with patch.dict(sys.modules, {"sentence_transformers": None}):
        with pytest.raises(ImportError, match="sentence-transformers"):
            _require_sentence_transformers()


# ---------------------------------------------------------------------------
# _get_embedding_model — cache behaviour
# ---------------------------------------------------------------------------


def test_get_embedding_model_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model is created once and cached for repeated calls with the same name."""
    call_count = {"n": 0}

    # Save + clear the real cache
    original_cache = dict(vector_rag_mod._MODEL_CACHE)
    vector_rag_mod._MODEL_CACHE.pop("_test_cache_key_", None)

    class _FakeST:
        """Test fake st."""

        def __init__(self, name: str) -> None:
            """Test init."""

            call_count["n"] += 1

    def _fake_require() -> type:
        """Test fake require."""

        return _FakeST

    monkeypatch.setattr(vector_rag_mod, "_require_sentence_transformers", _fake_require)

    _get_embedding_model("_test_cache_key_")
    _get_embedding_model("_test_cache_key_")  # second call — uses cache

    assert call_count["n"] == 1

    # Restore
    vector_rag_mod._MODEL_CACHE.pop("_test_cache_key_", None)
    vector_rag_mod._MODEL_CACHE.update(original_cache)


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------


def test_chunk_text_empty() -> None:
    """Test chunk text empty."""

    assert _chunk_text("") == []
    assert _chunk_text("   ") == []


def test_chunk_text_small() -> None:
    """Test chunk text small."""

    result = _chunk_text("Hello world", chunk_size=100)
    assert result == ["Hello world"]


def test_chunk_text_multi_chunk() -> None:
    """Test chunk text multi chunk."""

    text = "A" * 300
    chunks = _chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 100


# ---------------------------------------------------------------------------
# VectorRAGIndex — ingest
# ---------------------------------------------------------------------------


def test_ingest_text_empty_returns_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test ingest text empty returns zero."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    assert idx.ingest_text("") == 0
    assert idx.ingest_text("   ") == 0


def test_ingest_text_adds_single_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test ingest text adds single chunk."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    count = idx.ingest_text("Hello SolidWorks world.", source="test.md")
    assert count == 1
    assert idx.chunk_count == 1


def test_ingest_text_deduplication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test ingest text deduplication."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    idx.ingest_text("Hello world.", source="a.md")
    second = idx.ingest_text("Hello world.", source="b.md")  # duplicate
    assert second == 0
    assert idx.chunk_count == 1


def test_ingest_text_dedup_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test ingest text dedup disabled."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    idx.ingest_text("Hello world.", source="a.md")
    second = idx.ingest_text("Hello world.", source="b.md", deduplicate=False)
    assert second == 1
    assert idx.chunk_count == 2


def test_ingest_large_text_multi_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test ingest large text multi chunk."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    long_text = "SolidWorks feature. " * 100  # > 1000 chars
    count = idx.ingest_text(long_text, source="long.md", chunk_size=200, overlap=20)
    assert count > 1


def test_ingest_with_tags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test ingest with tags."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    count = idx.ingest_text("Text.", source="s.md", tags=["sw", "ref"])
    assert count == 1
    assert idx._meta[0]["tags"] == ["sw", "ref"]


# ---------------------------------------------------------------------------
# VectorRAGIndex — query
# ---------------------------------------------------------------------------


def test_query_empty_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test query empty index."""

    monkeypatch.setattr(
        vector_rag_mod, "_get_embedding_model", lambda *a, **k: _fake_model()
    )
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    assert idx.query("solidworks sketch") == []


def test_query_returns_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test query returns results."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)
    idx = VectorRAGIndex(namespace="test", rag_dir=tmp_path)
    idx.ingest_text("Create a sketch in SolidWorks.", source="sw.md")
    results = idx.query("sketch")
    assert len(results) == 1
    assert "score" in results[0]
    assert results[0]["source"] == "sw.md"


# ---------------------------------------------------------------------------
# VectorRAGIndex — save / load
# ---------------------------------------------------------------------------


def test_save_no_op_when_empty(tmp_path: Path) -> None:
    """Test save no op when empty."""

    idx = VectorRAGIndex(namespace="empty", rag_dir=tmp_path)
    idx.save()  # should not raise; nothing written
    assert not (tmp_path / "empty.faiss").exists()


def test_save_and_load_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test save and load roundtrip."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)
    idx = VectorRAGIndex(namespace="myns", rag_dir=tmp_path)
    idx.ingest_text("Sketch entities in SolidWorks.", source="a.md")
    idx.save()

    idx2 = VectorRAGIndex.load(namespace="myns", rag_dir=tmp_path)
    assert idx2.chunk_count == 1
    assert idx2.index_path.endswith("myns.faiss")


def test_load_missing_files_returns_empty(tmp_path: Path) -> None:
    """Test load missing files returns empty."""

    idx = VectorRAGIndex.load(namespace="nonexistent", rag_dir=tmp_path)
    assert idx.chunk_count == 0


def test_load_corrupted_files(tmp_path: Path) -> None:
    """Load() handles corrupt files gracefully and returns empty index."""
    faiss_path = tmp_path / "bad.faiss"
    meta_path = tmp_path / "bad.meta.json"
    faiss_path.write_bytes(b"not-valid-faiss-data")
    meta_path.write_text("{}", encoding="utf-8")
    idx = VectorRAGIndex.load(namespace="bad", rag_dir=tmp_path)
    assert idx.chunk_count == 0


# ---------------------------------------------------------------------------
# query_design_knowledge
# ---------------------------------------------------------------------------


def test_query_design_knowledge_empty_index(tmp_path: Path) -> None:
    """Test query design knowledge empty index."""

    result = query_design_knowledge("sketch", rag_dir=tmp_path)
    assert result == ""


def test_query_design_knowledge_below_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test query design knowledge below threshold."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)
    idx = VectorRAGIndex(namespace="engineering-reference", rag_dir=tmp_path)
    idx.ingest_text("Sketch entities in SolidWorks.", source="a.md")
    idx.save()
    with patch.object(
        VectorRAGIndex,
        "query",
        return_value=[{"score": 0.0, "source": "a.md", "text": "Sketch entities."}],
    ):
        result = query_design_knowledge("sketch", rag_dir=tmp_path, score_threshold=0.5)
    assert result == ""


def test_query_design_knowledge_returns_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test query design knowledge returns context."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)
    idx = VectorRAGIndex(namespace="engineering-reference", rag_dir=tmp_path)
    idx.ingest_text("SolidWorks sketch reference guide.", source="guide.md")
    idx.save()
    with patch.object(
        VectorRAGIndex,
        "query",
        return_value=[
            {"score": 0.9, "source": "guide.md", "text": "SolidWorks sketch."}
        ],
    ):
        result = query_design_knowledge("sketch", rag_dir=tmp_path)
    assert "Relevant Design Knowledge" in result
    assert "guide.md" in result


def test_query_design_knowledge_import_error(tmp_path: Path) -> None:
    """Test query design knowledge import error."""

    with patch.object(VectorRAGIndex, "load", side_effect=ImportError("no faiss")):
        result = query_design_knowledge("test", rag_dir=tmp_path)
    assert result == ""


def test_query_design_knowledge_generic_error(tmp_path: Path) -> None:
    """Test query design knowledge generic error."""

    with patch.object(VectorRAGIndex, "load", side_effect=RuntimeError("disk error")):
        result = query_design_knowledge("test", rag_dir=tmp_path)
    assert result == ""


# ---------------------------------------------------------------------------
# build_solidworks_api_docs_index
# ---------------------------------------------------------------------------


def test_build_solidworks_api_docs_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test build solidworks api docs index."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)

    docs_json = {
        "solidworks_version": "2026",
        "com_objects": {
            "ISldWorks": {
                "methods": ["NewDocument", "OpenDoc"],
                "properties": ["ActiveDoc"],
            },
            "IModelDoc2": {
                "methods": ["Save3"],
                "properties": [],
            },
        },
        "vba_references": {
            "SldWorks 2026 Type Library": {"status": "available", "version": "34.0"},
            "Microsoft Excel 2016": {"status": "available", "version": "1.9"},
        },
    }
    docs_path = tmp_path / "docs.json"
    docs_path.write_text(json.dumps(docs_json), encoding="utf-8")

    idx = build_solidworks_api_docs_index(docs_path, rag_dir=tmp_path)
    assert idx.chunk_count >= 2  # at least ISldWorks + IModelDoc2; VBA chunk optional


def test_build_solidworks_api_docs_index_no_sw_vba_libs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No SolidWorks VBA refs → VBA chunk is skipped, only COM chunks added."""
    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)

    docs_json = {
        "solidworks_version": "2026",
        "com_objects": {
            "ISldWorks": {"methods": ["NewDocument"], "properties": []},
        },
        "vba_references": {
            "Microsoft Excel": {"status": "available", "version": "1.9"},
        },
    }
    docs_path = tmp_path / "docs2.json"
    docs_path.write_text(json.dumps(docs_json), encoding="utf-8")

    idx = build_solidworks_api_docs_index(docs_path, rag_dir=tmp_path)
    assert idx.chunk_count >= 1


# ---------------------------------------------------------------------------
# query_solidworks_api_docs
# ---------------------------------------------------------------------------


def test_query_solidworks_api_docs_no_index(tmp_path: Path) -> None:
    """Test query solidworks api docs no index."""

    result = query_solidworks_api_docs("create part", rag_dir=tmp_path)
    assert result == ""


def test_query_solidworks_api_docs_empty_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Returns '' when index has zero chunks."""
    with patch.object(VectorRAGIndex, "load") as mock_load:
        mock_idx = MagicMock()
        mock_idx.chunk_count = 0
        mock_load.return_value = mock_idx
        result = query_solidworks_api_docs("sketch", rag_dir=tmp_path)
    assert result == ""


def test_query_solidworks_api_docs_returns_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test query solidworks api docs returns context."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)

    idx = VectorRAGIndex(namespace="solidworks-api-docs", rag_dir=tmp_path)
    idx.ingest_text("ISldWorks: NewDocument, OpenDoc", source="com:ISldWorks")
    idx.save()

    with patch.object(
        VectorRAGIndex,
        "query",
        return_value=[
            {"score": 0.8, "source": "com:ISldWorks", "text": "ISldWorks: NewDocument"}
        ],
    ):
        result = query_solidworks_api_docs("create part", rag_dir=tmp_path)
    assert "SolidWorks API Reference" in result
    assert "ISldWorks" in result


def test_query_solidworks_api_docs_below_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test query solidworks api docs below threshold."""

    fake = _fake_model()
    monkeypatch.setattr(vector_rag_mod, "_get_embedding_model", lambda *a, **k: fake)

    idx = VectorRAGIndex(namespace="solidworks-api-docs", rag_dir=tmp_path)
    idx.ingest_text("ISldWorks methods.", source="com:ISldWorks")
    idx.save()

    with patch.object(
        VectorRAGIndex,
        "query",
        return_value=[{"score": 0.05, "source": "com:ISldWorks", "text": "ISldWorks."}],
    ):
        result = query_solidworks_api_docs(
            "sketch", rag_dir=tmp_path, score_threshold=0.5
        )
    assert result == ""


def test_query_solidworks_api_docs_import_error(tmp_path: Path) -> None:
    """Test query solidworks api docs import error."""

    with patch.object(VectorRAGIndex, "load", side_effect=ImportError("no faiss")):
        result = query_solidworks_api_docs("test", rag_dir=tmp_path)
    assert result == ""
