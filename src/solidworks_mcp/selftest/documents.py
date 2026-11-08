"""Keep the selftest away from the user's documents.

The guard notes which documents are open before the selftest starts and
gives it a fresh temporary folder to save into. On the way out, also after
an error, it closes, unsaved, only the documents the selftest made, then
deletes the folder. A document that was open before is never activated,
saved or closed.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Any

from .results import ToolCaller, ToolFailed

#: Close order: a drawing or assembly before the parts it references.
_CLOSE_ORDER = {"Drawing": 0, "Assembly": 1}


class DocumentGuard:
    """An async context manager owning the selftest's folder and documents."""

    def __init__(self, call: ToolCaller) -> None:
        """Use ``call`` to list, activate and close documents.

        Args:
            call: The selftest's tool caller.
        """
        self._call = call
        self._baseline: set[str] = set()
        self._folder: Path | None = None
        self.problems: list[str] = []

    async def __aenter__(self) -> DocumentGuard:
        """Note the open documents and make the folder.

        Returns:
            DocumentGuard: This guard, with ``folder`` set.
        """
        self._baseline = {d["title"] for d in await self._documents() if d["title"]}
        self._folder = Path(tempfile.mkdtemp(prefix="solidworks-mcp-selftest-"))
        return self

    @property
    def folder(self) -> Path:
        """The selftest's temporary folder; only inside ``async with``.

        Raises:
            RuntimeError: The guard has not been entered.
        """
        if self._folder is None:
            raise RuntimeError("DocumentGuard is used outside `async with`")
        return self._folder

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the selftest's documents and delete its folder.

        Args:
            exc_type: The exception's type, if one is propagating.
            exc: The exception, if one is propagating.
            traceback: Its traceback.
        """
        await self.cleanup()

    def is_ours(self, document: dict[str, Any]) -> bool:
        """Whether the selftest made ``document``.

        Args:
            document: An entry from ``list_open_documents``.

        Returns:
            bool: True when it is new since the start and was never saved,
            or was saved inside the selftest's folder.
        """
        if not document.get("title") or document["title"] in self._baseline:
            return False
        path = document.get("path") or ""
        if not path:
            return True
        folder = os.path.normcase(str(self.folder.resolve()))
        return os.path.normcase(str(Path(path).resolve())).startswith(folder + os.sep)

    async def cleanup(self) -> None:
        """Close the selftest's documents, unsaved, then delete its folder.

        A failure is recorded in ``problems``, never raised, so it can't hide
        the results it follows.
        """
        try:
            documents = await self._documents()
        except ToolFailed as exc:
            self.problems.append(f"could not list the open documents: {exc.message}")
            documents = []
        ours = sorted(
            (d for d in documents if self.is_ours(d)),
            key=lambda d: _CLOSE_ORDER.get(str(d.get("type")), 2),
        )
        for document in ours:
            try:
                await self._call(
                    "activate_document",
                    {"title_or_path": document["title"]},
                    record=False,
                )
                await self._call("close_model", {"save": False}, record=False)
            except ToolFailed as exc:
                self.problems.append(
                    f"could not close {document['title']}: {exc.message}"
                )
        shutil.rmtree(self.folder, ignore_errors=True)
        if self.folder.exists():
            self.problems.append(f"could not delete {self.folder}")
        self._folder = None

    async def _documents(self) -> list[dict[str, Any]]:
        """The open documents, from ``list_open_documents``."""
        reply = await self._call("list_open_documents", record=False)
        return list(reply.get("documents") or [])
