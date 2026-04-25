"""FAISS-backed vector RAG index for SolidWorks design knowledge.

Supports local file and URL ingestion (PDF, Markdown, plain text, HTML), embedding via
sentence-transformers (all-MiniLM-L6-v2 by default), and FAISS cosine-similarity search.

Usage::

from solidworks_mcp.agents.vector_rag import VectorRAGIndex

# Build / update an index idx = VectorRAGIndex(namespace="3d-print-design")
idx.ingest_text("snap-fit-guide.md content …", source="snap-fit-guide.md") idx.save()

# Query later idx2 = VectorRAGIndex.load(namespace="3d-print-design") hits =
idx2.query("snap fit cantilever deflection", top_k=5) for hit in hits:
print(hit["score"], hit["text"][:120])
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RAG_DIR = Path(".solidworks_mcp") / "rag"
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150

# ---------------------------------------------------------------------------
# Lazy imports so the module loads even without optional deps
# ---------------------------------------------------------------------------


def _require_faiss():  # noqa: ANN202  # pragma: no cover
    """Return the required require faiss.

    Returns:
        Any: The result produced by the operation.

    Raises:
        ImportError: Faiss-cpu is required for vector RAG. Install with: pip install faiss-
                     cpu.
    """

    try:
        import faiss  # type: ignore[import]

        return faiss
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "faiss-cpu is required for vector RAG. Install with: pip install faiss-cpu"
        ) from exc


def _require_sentence_transformers():  # noqa: ANN202  # pragma: no cover
    """Return the required require sentence transformers.

    Returns:
        Any: The result produced by the operation.

    Raises:
        ImportError: Sentence-transformers is required for vector RAG. Install with: pip
                     install sentence-transformers.
    """

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]

        return SentenceTransformer
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "sentence-transformers is required for vector RAG. "
            "Install with: pip install sentence-transformers"
        ) from exc


# ---------------------------------------------------------------------------
# Module-level model cache — one SentenceTransformer instance per model name,
# shared across all VectorRAGIndex instances in the process.
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[str, Any] = {}


def _get_embedding_model(model_name: str = DEFAULT_MODEL) -> Any:
    """Return a cached SentenceTransformer, loading it on first call.

    Args:
        model_name (str): Embedding model name to use. Defaults to DEFAULT_MODEL.

    Returns:
        Any: The result produced by the operation.
    """
    if model_name not in _MODEL_CACHE:
        SentenceTransformer = _require_sentence_transformers()
        logger.info("Loading embedding model %s …", model_name)
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------


def _chunk_text(
    text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    """Build internal chunk text.

    Args:
        text (str): Input text processed by the operation.
        chunk_size (int): Maximum number of characters to keep in each chunk. Defaults to
                          DEFAULT_CHUNK_SIZE.
        overlap (int): Number of overlapping characters between chunks. Defaults to
                       DEFAULT_OVERLAP.

    Returns:
        list[str]: A list containing the resulting items.
    """

    normalized = (text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class VectorRAGIndex:
    """FAISS cosine-similarity index for a named namespace of design knowledge.

    Files on disk: - ``{rag_dir}/{namespace}.faiss``   – FAISS flat-IP index -
    ``{rag_dir}/{namespace}.meta.json`` – chunk metadata (source, text, etc.)

    Args:
        namespace (str): Namespace used to isolate stored data. Defaults to "engineering-
                         reference".
        model_name (str): Embedding model name to use. Defaults to DEFAULT_MODEL.
        rag_dir (Path | None): Directory where RAG assets are stored. Defaults to None.

    Attributes:
        _faiss_path (Any): The faiss path value.
        _meta_path (Any): The meta path value.
        model_name (Any): The model name value.
        namespace (Any): The namespace value.
        rag_dir (Any): The rag dir value.
    """

    def __init__(
        self,
        namespace: str = "engineering-reference",
        *,
        model_name: str = DEFAULT_MODEL,
        rag_dir: Path | None = None,
    ) -> None:
        """Initialize the vector ragindex.

        Args:
            namespace (str): Namespace used to isolate stored data. Defaults to "engineering-
                             reference".
            model_name (str): Embedding model name to use. Defaults to DEFAULT_MODEL.
            rag_dir (Path | None): Directory where RAG assets are stored. Defaults to None.

        Returns:
            None: None.
        """

        self.namespace = namespace
        self.model_name = model_name
        self.rag_dir = rag_dir or DEFAULT_RAG_DIR
        self._faiss_path = self.rag_dir / f"{namespace}.faiss"
        self._meta_path = self.rag_dir / f"{namespace}.meta.json"
        self._index: Any = None  # faiss.IndexFlatIP
        self._meta: list[dict[str, Any]] = []
        self._dim: int | None = None
        # Model is cached at module level in _MODEL_CACHE; no instance field needed.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> Any:
        """Build internal model.

        Returns:
            Any: The result produced by the operation.
        """

        return _get_embedding_model(self.model_name)

    def _embed(self, texts: list[str]) -> Any:
        """Build internal embed.

        Args:
            texts (list[str]): The texts value.

        Returns:
            Any: The result produced by the operation.
        """

        import numpy as np  # type: ignore[import]

        model = self._get_model()
        vecs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.astype(np.float32)

    def _init_index(self, dim: int) -> None:
        """Initialize the init index.

        Args:
            dim (int): The dim value.

        Returns:
            None: None.
        """

        faiss = _require_faiss()
        self._dim = dim
        self._index = faiss.IndexFlatIP(dim)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_text(
        self,
        text: str,
        *,
        source: str = "unknown",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
        tags: list[str] | None = None,
        deduplicate: bool = True,
    ) -> int:
        """Chunk *text*, embed chunks, add to FAISS index.

        Returns the number of new chunks added.

        Args:
            text (str): Input text processed by the operation.
            source (str): Source label associated with the input content. Defaults to "unknown".
            chunk_size (int): Maximum number of characters to keep in each chunk. Defaults to
                              DEFAULT_CHUNK_SIZE.
            overlap (int): Number of overlapping characters between chunks. Defaults to
                           DEFAULT_OVERLAP.
            tags (list[str] | None): Optional tags associated with the input content. Defaults
                                     to None.
            deduplicate (bool): Whether duplicate content should be skipped. Defaults to True.

        Returns:
            int: The computed numeric result.
        """

        chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            return 0

        # Optional deduplication by exact text hash
        existing_texts: set[str] = set()
        if deduplicate:
            existing_texts = {m["text"] for m in self._meta}

        new_chunks = [c for c in chunks if c not in existing_texts]
        if not new_chunks:
            return 0

        vecs = self._embed(new_chunks)

        if self._index is None:
            self._init_index(vecs.shape[1])

        # Pad if needed (shouldn't happen but be safe)
        assert vecs.shape[1] == self._dim, "Embedding dim mismatch"

        self._index.add(vecs)

        ts = time.time()
        for _i, chunk in enumerate(new_chunks):
            self._meta.append(
                {
                    "id": f"{self.namespace}-{len(self._meta)}",
                    "source": source,
                    "text": chunk,
                    "tags": tags or [],
                    "ingested_at": ts,
                }
            )

        logger.info(
            "Ingested %d chunks from '%s' into namespace '%s'",
            len(new_chunks),
            source,
            self.namespace,
        )
        return len(new_chunks)

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search. Returns list of ``{score, id, source, text, tags}`` dicts.

        sorted by cosine similarity descending.

        Args:
            query_text (str): Query text used to search the index.
            top_k (int): Maximum number of matches to return. Defaults to 5.

        Returns:
            list[dict[str, Any]]: A list containing the resulting items.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        vec = self._embed([query_text])
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx < 0:
                continue
            meta = self._meta[idx].copy()
            meta["score"] = float(score)
            results.append(meta)
        return results

    def save(self) -> None:
        """Persist index and metadata to disk.

        Returns:
            None: None.
        """
        if self._index is None:
            return
        faiss = _require_faiss()
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._faiss_path))
        self._meta_path.write_text(
            json.dumps(
                {"namespace": self.namespace, "dim": self._dim, "chunks": self._meta},
                indent=2,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
        logger.info(
            "Saved FAISS index (%d vectors) to %s", self._index.ntotal, self._faiss_path
        )

    @classmethod
    def load(
        cls,
        namespace: str = "engineering-reference",
        *,
        model_name: str = DEFAULT_MODEL,
        rag_dir: Path | None = None,
    ) -> VectorRAGIndex:
        """Load an existing index from disk. Returns an empty index if not found.

        Args:
            namespace (str): Namespace used to isolate stored data. Defaults to "engineering-
                             reference".
            model_name (str): Embedding model name to use. Defaults to DEFAULT_MODEL.
            rag_dir (Path | None): Directory where RAG assets are stored. Defaults to None.

        Returns:
            VectorRAGIndex: The result produced by the operation.
        """
        inst = cls(namespace=namespace, model_name=model_name, rag_dir=rag_dir)
        if not inst._faiss_path.exists() or not inst._meta_path.exists():
            return inst
        try:
            faiss = _require_faiss()
            inst._index = faiss.read_index(str(inst._faiss_path))
            raw = json.loads(inst._meta_path.read_text(encoding="utf-8"))
            inst._meta = raw.get("chunks", [])
            inst._dim = raw.get("dim")
            logger.info(
                "Loaded FAISS index '%s' (%d vectors)", namespace, inst._index.ntotal
            )
        except Exception as exc:
            logger.warning("Failed to load FAISS index '%s': %s", namespace, exc)
            inst._index = None
            inst._meta = []
        return inst

    @property
    def chunk_count(self) -> int:
        """Provide chunk count support for the vector ragindex.

        Returns:
            int: The computed numeric result.
        """

        return len(self._meta)

    @property
    def index_path(self) -> str:
        """Provide index path support for the vector ragindex.

        Returns:
            str: The resulting text value.
        """

        return str(self._faiss_path)


# ---------------------------------------------------------------------------
# Convenience query helper (used by service.py for LLM context injection)
# ---------------------------------------------------------------------------


def query_design_knowledge(
    query: str,
    *,
    namespace: str = "engineering-reference",
    top_k: int = 5,
    rag_dir: Path | None = None,
    score_threshold: float = 0.25,
) -> str:
    """Query the FAISS index and return a formatted context string for LLM injection.

    Returns empty string if no index or no relevant results.

    Args:
        query (str): Query text used for the operation.
        namespace (str): Namespace used to isolate stored data. Defaults to "engineering-
                         reference".
        top_k (int): Maximum number of matches to return. Defaults to 5.
        rag_dir (Path | None): Directory where RAG assets are stored. Defaults to None.
        score_threshold (float): The score threshold value. Defaults to 0.25.

    Returns:
        str: The resulting text value.
    """
    try:
        idx = VectorRAGIndex.load(namespace=namespace, rag_dir=rag_dir)
        hits = idx.query(query, top_k=top_k)
        hits = [h for h in hits if h.get("score", 0) >= score_threshold]
        if not hits:
            return ""
        lines = [f"## Relevant Design Knowledge (from '{namespace}')"]
        for i, hit in enumerate(hits, 1):
            source = hit.get("source", "unknown")
            text = hit["text"].strip()
            lines.append(f"\n### [{i}] Source: {source}")
            lines.append(text)
        return "\n".join(lines)
    except ImportError:
        return ""  # FAISS not installed; graceful degradation
    except Exception as exc:
        logger.debug("RAG query failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# SolidWorks API docs RAG — build and query the COM/VBA index
# ---------------------------------------------------------------------------

SW_API_DOCS_NAMESPACE = "solidworks-api-docs"


def build_solidworks_api_docs_index(
    docs_json_path: Path,
    *,
    rag_dir: Path | None = None,
    namespace: str = SW_API_DOCS_NAMESPACE,
) -> VectorRAGIndex:
    """Ingest a ``solidworks_docs_index_*.json`` file into a FAISS namespace so.

    the SolidWorks COM/VBA API surface is searchable by Gemma and other agents.

    Each COM interface becomes its own chunk; the VBA TypeLib catalogue becomes a single
    chunk.  Call ``save()`` on the returned index to persist to disk.

    Parameters ---------- docs_json_path: Path to the JSON file produced by
    ``SolidWorksDocsDiscovery.save_index()``. rag_dir: Override for the FAISS storage
    directory. namespace: FAISS namespace name (default: ``"solidworks-api-docs"``).

    Returns ------- VectorRAGIndex A populated (but not yet saved) index.  Call ``.save()``
    after ingestion.

    Args:
        docs_json_path (Path): The docs json path value.
        rag_dir (Path | None): Directory where RAG assets are stored. Defaults to None.
        namespace (str): Namespace used to isolate stored data. Defaults to
                         SW_API_DOCS_NAMESPACE.

    Returns:
        VectorRAGIndex: The result produced by the operation.
    """
    raw = json.loads(docs_json_path.read_text(encoding="utf-8"))
    idx = VectorRAGIndex(namespace=namespace, rag_dir=rag_dir)

    # --- COM interfaces ---
    com_objects: dict[str, Any] = raw.get("com_objects", {})
    for iface_name, iface_data in com_objects.items():
        methods = iface_data.get("methods", [])
        props = iface_data.get("properties", [])
        lines = [
            f"SolidWorks COM Interface: {iface_name}",
            f"Methods ({len(methods)}): {', '.join(methods)}",
        ]
        if props:
            lines.append(f"Properties ({len(props)}): {', '.join(props)}")
        text = "\n".join(lines)
        idx.ingest_text(
            text,
            source=f"com:{iface_name}",
            tags=["solidworks-api", "com", iface_name.lower()],
        )

    # --- VBA TypeLib references (one chunk for available SW-related libs) ---
    vba_refs: dict[str, Any] = raw.get("vba_references", {})
    sw_libs = [
        f"{name} ({info.get('version', '')})"
        for name, info in vba_refs.items()
        if info.get("status") == "available"
        and any(
            kw in name.lower()
            for kw in ("solidworks", "sldworks", "cosmos", "simulation", "routing")
        )
    ]
    if sw_libs:
        vba_text = "SolidWorks VBA / COM TypeLib References (available):\n" + "\n".join(
            f"  - {lib}" for lib in sw_libs
        )
        idx.ingest_text(
            vba_text,
            source="vba:typelib-registry",
            tags=["solidworks-api", "vba", "typelib"],
        )

    sw_version = raw.get("solidworks_version") or "unknown"
    logger.info(
        "Built '%s' FAISS namespace: %d chunks (SW version: %s)",
        namespace,
        idx.chunk_count,
        sw_version,
    )
    return idx


def query_solidworks_api_docs(
    query: str,
    *,
    top_k: int = 5,
    rag_dir: Path | None = None,
    score_threshold: float = 0.20,
) -> str:
    """Semantic search over the SolidWorks COM/VBA API surface.

    Returns a formatted markdown context string ready to inject into an LLM system prompt,
    or an empty string if no relevant results are found.

    Parameters ---------- query: Natural-language question or task description. top_k:
    Maximum number of chunks to return. rag_dir: Override for the FAISS storage directory.
    score_threshold: Minimum cosine-similarity score (0–1) to include a chunk.

    Args:
        query (str): Query text used for the operation.
        top_k (int): Maximum number of matches to return. Defaults to 5.
        rag_dir (Path | None): Directory where RAG assets are stored. Defaults to None.
        score_threshold (float): The score threshold value. Defaults to 0.20.

    Returns:
        str: The resulting text value.
    """
    try:
        idx = VectorRAGIndex.load(namespace=SW_API_DOCS_NAMESPACE, rag_dir=rag_dir)
        if idx.chunk_count == 0:
            return ""
        hits = idx.query(query, top_k=top_k)
        hits = [h for h in hits if h.get("score", 0) >= score_threshold]
        if not hits:
            return ""
        lines = ["## SolidWorks API Reference (from local COM/VBA index)"]
        for i, hit in enumerate(hits, 1):
            source = hit.get("source", "unknown")
            text = hit["text"].strip()
            lines.append(f"\n### [{i}] {source}")
            lines.append(text)
        return "\n".join(lines)
    except ImportError:
        return ""  # FAISS not installed
    except Exception as exc:
        logger.debug("query_solidworks_api_docs failed: %s", exc)
        return ""
