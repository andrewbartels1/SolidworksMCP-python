"""Coverage tests for vector_rag without optional faiss/numpy dependencies."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.solidworks_mcp.agents.vector_rag as vr


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
