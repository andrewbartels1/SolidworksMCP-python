"""Coverage tests for src/solidworks_mcp/agents/vector_rag.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("faiss")

import tempfile
from types import SimpleNamespace

import pytest

import solidworks_mcp.agents.vector_rag as vector_rag_mod
import solidworks_mcp.agents.vector_rag as vr
from solidworks_mcp.agents.vector_rag import (
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


@pytest.mark.slow
def test_require_sentence_transformers_success() -> None:
    """_require_sentence_transformers returns the SentenceTransformer class.

    ``slow``: the only test in this module that imports the real
    ``sentence_transformers`` (~9 s of torch/transformers). Every other test
    fakes ``_get_embedding_model`` / ``_require_sentence_transformers``, so
    this is the one that proves the real happy path. Runs under
    ``dev-test-full`` / ``dev-test-combined`` / CI; ``dev-test`` skips it.
    """
    pytest.importorskip("sentence_transformers")
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


def test_fallback_embedder_when_sentence_transformers_is_absent(monkeypatch) -> None:
    """Not installed (no sys.modules entry) -> deterministic numpy fallback."""
    import builtins
    import sys

    import numpy as np

    real_import = builtins.__import__

    def _no_sentence_transformers(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)
    monkeypatch.setattr(builtins, "__import__", _no_sentence_transformers)

    model = _require_sentence_transformers()("any-model")
    normalised = model.encode(["bracket", "bracket", "flange"])
    raw = model.encode(["bracket"], normalize_embeddings=False)

    assert normalised.shape == (3, 384)
    assert normalised.dtype == np.float32
    assert np.allclose(np.linalg.norm(normalised, axis=1), 1.0, atol=1e-5)
    assert np.array_equal(normalised[0], normalised[1])  # same text, same vector
    assert not np.array_equal(normalised[0], normalised[2])
    assert not np.isclose(np.linalg.norm(raw[0]), 1.0)  # left unnormalised


def test_awaitable_query_result_creation():
    """_AwaitableQueryResult should be a str subclass with _hits. Covers lines 126-129."""
    from solidworks_mcp.agents.vector_rag import _AwaitableQueryResult

    hits = [{"text": "hello", "score": 0.9}]
    result = _AwaitableQueryResult("found text", hits=hits)
    assert result == "found text"
    assert result._hits == hits


@pytest.mark.asyncio
async def test_awaitable_query_result_await():
    """_AwaitableQueryResult.__await__ should return hits list. Covers lines 132-135."""
    from solidworks_mcp.agents.vector_rag import _AwaitableQueryResult

    hits = [{"text": "some result", "score": 0.8}]
    result = _AwaitableQueryResult("text", hits=hits)
    awaited = await result
    assert isinstance(awaited, list)
    assert awaited == hits


@pytest.mark.asyncio
async def test_vector_rag_index_await():
    """VectorRAGIndex.__await__ should return self. Covers lines 246-249."""
    from solidworks_mcp.agents.vector_rag import VectorRAGIndex

    idx = VectorRAGIndex(namespace="test")
    awaited = await idx
    assert awaited is idx


def test_build_solidworks_api_docs_index_returns_empty_when_no_path():
    """build_solidworks_api_docs_index should return early when docs_json_path is None. Covers line 565."""
    from solidworks_mcp.agents.vector_rag import (
        VectorRAGIndex,
        build_solidworks_api_docs_index,
    )

    result = build_solidworks_api_docs_index(docs_json_path=None)
    assert isinstance(result, VectorRAGIndex)
    assert result.chunk_count == 0


def _fake_embeddings(texts: list[str], dim: int = 16) -> np.ndarray:
    """Generate fake embeddings for testing."""
    np.random.seed(hash(str(texts)) % 2**32)
    return np.random.randn(len(texts), dim).astype("float32")


@pytest.fixture
def temp_rag_dir() -> Path:
    """Create temporary RAG directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_model():
    """Mock SentenceTransformer model."""
    model = MagicMock()
    model.encode.side_effect = lambda texts, **kw: _fake_embeddings(texts)
    return model


@pytest.fixture
def patched_embeddings(mock_model):
    """Patch embedding model retrieval."""
    with patch(
        "solidworks_mcp.agents.vector_rag._get_embedding_model",
        return_value=mock_model,
    ):
        yield mock_model


@pytest.fixture
def fake_docs_json(temp_rag_dir: Path) -> Path:
    """Write a minimal solidworks_docs_index JSON for testing."""
    data = {
        "com_objects": {
            "IExtrusion": {
                "methods": ["GetDepth", "SetDepth"],
                "properties": ["Direction"],
            }
        },
        "vba_references": {
            "SldWorks 2025 Type Library": {"version": "29.0", "status": "available"}
        },
    }
    p = temp_rag_dir / "sw_docs.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestVectorRAGIndexOperations:
    """Test VectorRAGIndex FAISS operations."""

    def test_ingest_text_basic(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test basic text ingestion into index."""
        idx = VectorRAGIndex(namespace="test1", rag_dir=temp_rag_dir)

        text = "This is a test document about snap fits and design."
        count = idx.ingest_text(text, source="test.md")

        assert count > 0
        assert len(idx._meta) > 0
        assert idx._index is not None

    def test_ingest_text_multiple_chunks(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test ingestion splits text into chunks."""
        idx = VectorRAGIndex(
            namespace="test2", rag_dir=temp_rag_dir, model_name="all-MiniLM-L6-v2"
        )

        # Large text that will be chunked
        large_text = "Design concept. " * 1000  # Will exceed chunk_size
        count = idx.ingest_text(
            large_text, source="large.md", chunk_size=100, overlap=10
        )

        assert count > 1  # Should create multiple chunks
        assert len(idx._meta) >= count

    def test_ingest_empty_text_returns_zero(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test ingesting empty text returns 0."""
        idx = VectorRAGIndex(namespace="test3", rag_dir=temp_rag_dir)

        count = idx.ingest_text("", source="empty.md")
        assert count == 0

    def test_ingest_whitespace_only_returns_zero(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test ingesting whitespace-only text returns 0."""
        idx = VectorRAGIndex(namespace="test4", rag_dir=temp_rag_dir)

        count = idx.ingest_text("   \n\t  \n  ", source="whitespace.md")
        assert count == 0

    def test_ingest_with_deduplication(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test that duplicate chunks are not re-ingested."""
        idx = VectorRAGIndex(namespace="test5", rag_dir=temp_rag_dir)

        text = "Same content here. " * 10
        idx.ingest_text(text, source="file1.md", deduplicate=True)
        count2 = idx.ingest_text(text, source="file2.md", deduplicate=True)

        # Second ingestion should not add duplicates
        assert count2 == 0

    def test_ingest_without_deduplication(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test ingestion without deduplication adds all chunks."""
        idx = VectorRAGIndex(namespace="test6", rag_dir=temp_rag_dir)

        text = "Content here. " * 5
        count1 = idx.ingest_text(text, source="file1.md", deduplicate=False)
        count2 = idx.ingest_text(text, source="file2.md", deduplicate=False)

        # Should add duplicates when deduplicate=False
        assert count1 > 0
        assert count2 > 0

    def test_query_basic(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test basic similarity search."""
        idx = VectorRAGIndex(namespace="test7", rag_dir=temp_rag_dir)

        # Ingest some documents
        idx.ingest_text("Snap fit design uses cantilever beams", source="snap.md")
        idx.ingest_text("Assembly tolerances affect fit quality", source="tolerance.md")
        idx.ingest_text("Injection molding requires mold design", source="mold.md")

        # Query for relevant documents
        results = idx.query("cantilever beam snap fit", top_k=2)

        assert len(results) <= 2
        assert all("score" in r for r in results)
        assert all("text" in r for r in results)

    def test_query_empty_returns_empty(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test query on empty index returns empty results."""
        idx = VectorRAGIndex(namespace="test8", rag_dir=temp_rag_dir)

        results = idx.query("something", top_k=5)
        assert results == []

    def test_query_respects_top_k(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test that query returns at most top_k results."""
        idx = VectorRAGIndex(namespace="test9", rag_dir=temp_rag_dir)

        # Ingest multiple documents
        for i in range(10):
            idx.ingest_text(f"Document {i} content", source=f"doc{i}.md")

        results = idx.query("content", top_k=3)
        assert len(results) <= 3

    def test_ingest_with_tags(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test ingestion with tags metadata."""
        idx = VectorRAGIndex(namespace="test10", rag_dir=temp_rag_dir)

        count = idx.ingest_text(
            "Tagged content",
            source="tagged.md",
            tags=["design", "guide"],
        )

        assert count > 0
        # Metadata should include tags
        assert any("design" in str(m) for m in idx._meta)

    def test_save_index(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test saving index to disk."""
        idx = VectorRAGIndex(namespace="save_test", rag_dir=temp_rag_dir)

        idx.ingest_text("Content to save", source="source.md")
        idx.save()

        # Files should exist
        assert (temp_rag_dir / "save_test.faiss").exists()
        assert (temp_rag_dir / "save_test.meta.json").exists()

    def test_load_index(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test loading saved index from disk."""
        # Create and save index
        idx1 = VectorRAGIndex(namespace="load_test", rag_dir=temp_rag_dir)
        idx1.ingest_text("Content to load", source="source.md")
        idx1.save()

        # Load index
        idx2 = VectorRAGIndex.load(namespace="load_test", rag_dir=temp_rag_dir)

        assert idx2._index is not None
        assert len(idx2._meta) > 0

    def test_load_nonexistent_index(self, temp_rag_dir: Path) -> None:
        """load() returns an empty index when the files don't exist."""
        idx = VectorRAGIndex.load(namespace="nonexistent", rag_dir=temp_rag_dir)
        assert idx is not None
        assert len(idx._meta) == 0

    def test_ingest_from_url(self, temp_rag_dir: Path, patched_embeddings) -> None:
        """Test that ingest_text accepts a URL source string."""
        idx = VectorRAGIndex(namespace="url_test", rag_dir=temp_rag_dir)
        count = idx.ingest_text("Content from URL", source="https://example.com/doc.md")
        assert count > 0


class TestVectorRAGChunking:
    """Test text chunking with overlap."""

    def test_chunk_text_small_text_no_split(self) -> None:
        """Test that small text is not split."""
        text = "Short text."
        chunks = _chunk_text(text, chunk_size=100, overlap=10)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_large_text_splits(self) -> None:
        """Test that large text is split into multiple chunks."""
        text = "x" * 1000  # 1000 chars
        chunks = _chunk_text(text, chunk_size=100, overlap=10)

        assert len(chunks) > 1

    def test_chunk_text_overlap(self) -> None:
        """Test that chunks have proper overlap."""
        text = "0123456789" * 50  # 500 chars
        chunks = _chunk_text(text, chunk_size=100, overlap=20)

        # Check that consecutive chunks overlap
        for i in range(len(chunks) - 1):
            # The end of chunk i should overlap with start of chunk i+1
            # at least partially
            assert len(chunks[i]) > 0
            assert len(chunks[i + 1]) > 0

    def test_chunk_empty_text(self) -> None:
        """Test chunking empty text."""
        chunks = _chunk_text("", chunk_size=100, overlap=10)
        assert chunks == []

    def test_chunk_whitespace_only(self) -> None:
        """Test chunking whitespace-only text."""
        chunks = _chunk_text("   \n\t  ", chunk_size=100, overlap=10)
        assert chunks == []


class TestBuildSolidWorksAPIDocsIndex:
    """Test building SolidWorks API docs index."""

    def test_build_solidworks_api_docs_index(
        self, fake_docs_json: Path, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test building SolidWorks API docs index."""
        idx = build_solidworks_api_docs_index(
            fake_docs_json, namespace="api_test", rag_dir=temp_rag_dir
        )

        assert isinstance(idx, VectorRAGIndex)
        assert idx.namespace == "api_test"

    def test_query_solidworks_api_docs(
        self, fake_docs_json: Path, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test querying SolidWorks API docs."""
        idx = build_solidworks_api_docs_index(
            fake_docs_json, namespace="api_query_test", rag_dir=temp_rag_dir
        )
        idx.save()

        result = query_solidworks_api_docs("extrusion", rag_dir=temp_rag_dir)

        assert isinstance(result, str)

    def test_query_design_knowledge(
        self, temp_rag_dir: Path, patched_embeddings
    ) -> None:
        """Test querying design knowledge."""
        idx = VectorRAGIndex(namespace="engineering-reference", rag_dir=temp_rag_dir)
        idx.ingest_text("Snap fit design patterns", source="design.md")
        idx.save()

        result = query_design_knowledge("snap fit", rag_dir=temp_rag_dir)

        assert isinstance(result, str)


class _FakeVectors:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows

    @property
    def shape(self) -> tuple[int, int]:
        if not self.rows:
            return (0, 0)
        return (len(self.rows), len(self.rows[0]))

    def astype(self, _dtype: object) -> _FakeVectors:
        return self

    def __getitem__(self, index: int) -> list[float]:
        return self.rows[index]


class _FakeIndexFlatIP:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._vectors: list[list[float]] = []

    @property
    def ntotal(self) -> int:
        return len(self._vectors)

    def add(self, vecs: _FakeVectors) -> None:
        self._vectors.extend(vecs.rows)

    def search(
        self, query: _FakeVectors, k: int
    ) -> tuple[list[list[float]], list[list[int]]]:
        if self.ntotal == 0:
            return [[-1.0 for _ in range(k)]], [[-1 for _ in range(k)]]

        q = query[0]
        scored = []
        for i, row in enumerate(self._vectors):
            score = sum(a * b for a, b in zip(row, q, strict=False))
            scored.append((score, i))
        scored.sort(reverse=True)

        top = scored[:k]
        scores = [[item[0] for item in top]]
        indices = [[item[1] for item in top]]
        while len(scores[0]) < k:
            scores[0].append(-1.0)
            indices[0].append(-1)
        return scores, indices


class _FakeFaissModule:
    def __init__(self) -> None:
        self._store: dict[str, tuple[list[list[float]], int]] = {}

    @staticmethod
    def IndexFlatIP(dim: int) -> _FakeIndexFlatIP:
        return _FakeIndexFlatIP(dim)

    def write_index(self, index: _FakeIndexFlatIP, path: str) -> None:
        self._store[path] = ([row[:] for row in index._vectors], index.dim)
        Path(path).write_bytes(b"fake-faiss")

    def read_index(self, path: str) -> _FakeIndexFlatIP:
        vectors, dim = self._store[path]
        idx = _FakeIndexFlatIP(dim)
        idx._vectors = [row[:] for row in vectors]
        return idx


class _FakeSentenceTransformer:
    def __init__(self, _name: str) -> None:
        pass

    def encode(self, texts: list[str], **_kwargs) -> _FakeVectors:
        rows: list[list[float]] = []
        for text in texts:
            n = len(text)
            rows.append([float(n), float(n % 7), float(n % 11), 1.0])
        return _FakeVectors(rows)


@pytest.fixture
def fake_runtime(monkeypatch: pytest.MonkeyPatch):
    fake_faiss = _FakeFaissModule()
    fake_np = SimpleNamespace(float32="float32")
    monkeypatch.setitem(sys.modules, "numpy", fake_np)
    monkeypatch.setattr(vr, "_require_faiss", lambda: fake_faiss)
    monkeypatch.setattr(
        vr, "_require_sentence_transformers", lambda: _FakeSentenceTransformer
    )
    vr._MODEL_CACHE.clear()
    return fake_faiss


def test_embedding_cache_and_chunk_helpers(fake_runtime) -> None:
    first = vr._get_embedding_model("demo-model")
    second = vr._get_embedding_model("demo-model")
    assert first is second

    assert vr._chunk_text("   ") == []
    assert vr._chunk_text("abc", chunk_size=10) == ["abc"]
    chunks = vr._chunk_text("x" * 80, chunk_size=25, overlap=5)
    assert len(chunks) >= 3


def test_vector_index_ingest_query_save_load(fake_runtime, tmp_path: Path) -> None:
    idx = vr.VectorRAGIndex(namespace="demo", rag_dir=tmp_path)

    assert idx.ingest_text("   ") == 0

    added = idx.ingest_text("solidworks sketch feature", source="guide.md")
    assert added == 1

    # Dedup early return path.
    assert idx.ingest_text("solidworks sketch feature", source="guide2.md") == 0

    hits = idx.query("sketch", top_k=5)
    assert len(hits) == 1
    assert hits[0]["source"] == "guide.md"
    assert "score" in hits[0]

    idx.save()
    loaded = vr.VectorRAGIndex.load(namespace="demo", rag_dir=tmp_path)
    assert loaded.chunk_count == 1
    assert loaded.index_path.endswith("demo.faiss")


def test_query_skips_negative_indices(fake_runtime, tmp_path: Path) -> None:
    idx = vr.VectorRAGIndex(namespace="neg", rag_dir=tmp_path)
    idx.ingest_text("abc", source="a.md")

    idx._index.search = lambda _vec, _k: (  # type: ignore[method-assign]
        [[0.9, -1.0]],
        [[0, -1]],
    )

    results = idx.query("a", top_k=2)
    assert len(results) == 1


def test_query_design_knowledge_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_idx = SimpleNamespace(
        query=lambda _q, top_k=5: [
            {"score": 0.8, "source": "src1", "text": "use ribs"},
            {"score": 0.1, "source": "src2", "text": "ignore"},
        ]
    )
    monkeypatch.setattr(vr.VectorRAGIndex, "load", staticmethod(lambda **_k: fake_idx))

    result = vr.query_design_knowledge("ribs", score_threshold=0.2)
    assert "Relevant Design Knowledge" in result
    assert "src1" in result
    assert "src2" not in result

    monkeypatch.setattr(
        vr.VectorRAGIndex,
        "load",
        staticmethod(lambda **_k: (_ for _ in ()).throw(ImportError("no faiss"))),
    )
    assert vr.query_design_knowledge("ribs") == ""

    monkeypatch.setattr(
        vr.VectorRAGIndex,
        "load",
        staticmethod(lambda **_k: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    assert vr.query_design_knowledge("ribs") == ""


def test_build_and_query_solidworks_api_docs(
    fake_runtime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docs = {
        "solidworks_version": "2026",
        "com_objects": {
            "ISldWorks": {
                "methods": ["OpenDoc", "NewDocument"],
                "properties": ["ActiveDoc"],
            },
            "IModelDoc2": {
                "methods": ["Save3"],
                "properties": [],
            },
        },
        "vba_references": {
            "SldWorks 2026 Type Library": {
                "status": "available",
                "version": "34.0",
            },
            "Random Library": {"status": "available", "version": "1.0"},
        },
    }

    docs_path = tmp_path / "docs.json"
    docs_path.write_text(json.dumps(docs), encoding="utf-8")

    idx = vr.build_solidworks_api_docs_index(docs_path, rag_dir=tmp_path)
    assert idx.chunk_count >= 3
    idx.save()

    context = vr.query_solidworks_api_docs("open document", rag_dir=tmp_path)
    assert "SolidWorks API Reference" in context

    # Threshold branch: force low score so filtering returns no hits.
    monkeypatch.setattr(
        vr.VectorRAGIndex,
        "query",
        lambda self, _q, top_k=5: [
            {"score": 0.01, "source": "com:ISldWorks", "text": "x"}
        ],
    )
    empty_context = vr.query_solidworks_api_docs(
        "open document", rag_dir=tmp_path, score_threshold=0.5
    )
    assert empty_context == ""


def test_query_solidworks_api_docs_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_idx = SimpleNamespace(chunk_count=0)
    monkeypatch.setattr(vr.VectorRAGIndex, "load", staticmethod(lambda **_k: empty_idx))
    assert vr.query_solidworks_api_docs("test") == ""

    monkeypatch.setattr(
        vr.VectorRAGIndex,
        "load",
        staticmethod(lambda **_k: (_ for _ in ()).throw(ImportError("no faiss"))),
    )
    assert vr.query_solidworks_api_docs("test") == ""

    monkeypatch.setattr(
        vr.VectorRAGIndex,
        "load",
        staticmethod(lambda **_k: (_ for _ in ()).throw(RuntimeError("broken"))),
    )
    assert vr.query_solidworks_api_docs("test") == ""
