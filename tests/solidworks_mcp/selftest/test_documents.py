"""DocumentGuard closes only the selftest's documents and removes its folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.selftest.documents import DocumentGuard

from .caller_stub import CallerStub


class _Documents:
    """list_open_documents answering the baseline first, then later lists."""

    def __init__(self, *lists: list[dict]) -> None:
        self.lists = list(lists)

    def __call__(self, _args) -> dict:
        return {
            "documents": self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]
        }


def _doc(title: str, path: str = "", kind: str = "Part") -> dict:
    return {"title": title, "path": path, "type": kind}


@pytest.mark.asyncio
async def test_only_new_documents_unsaved_or_in_the_folder_are_closed() -> None:
    users = [_doc("bracket.SLDPRT", r"C:\work\bracket.SLDPRT"), _doc("Part1")]
    documents = _Documents(users, [])
    stub = CallerStub({"list_open_documents": documents})
    guard = DocumentGuard(stub)

    async with guard:
        folder = guard.folder
        assert folder.is_dir()
        documents.lists = [
            users
            + [
                _doc("Part7"),
                _doc("selftest_block.SLDPRT", str(folder / "selftest_block.SLDPRT")),
                _doc("other.SLDPRT", r"C:\work\other.SLDPRT"),
                _doc("Assem3", kind="Assembly"),
                _doc("", ""),
            ]
        ]

    closed = [a["title_or_path"] for n, a, _ in stub.log if n == "activate_document"]
    assert closed == ["Assem3", "Part7", "selftest_block.SLDPRT"]
    assert all(not record for _n, _a, record in stub.log)
    assert stub.calls == []
    assert not folder.exists()
    assert guard.problems == []


@pytest.mark.asyncio
async def test_cleanup_runs_after_an_exception_and_records_problems(
    monkeypatch, tmp_path: Path
) -> None:
    stub = CallerStub(
        {"list_open_documents": {"documents": []}},
    )
    guard = DocumentGuard(stub)
    monkeypatch.setattr(
        "solidworks_mcp.selftest.documents.shutil.rmtree", lambda *a, **k: None
    )

    with pytest.raises(RuntimeError, match="area bug"):
        async with guard:
            folder = guard.folder
            stub.replies["list_open_documents"] = {"documents": [_doc("Part2")]}
            stub.failures["close_model"] = "busy"
            raise RuntimeError("area bug")

    assert guard.problems == [
        "could not close Part2: busy",
        f"could not delete {folder}",
    ]
    folder.rmdir()


@pytest.mark.asyncio
async def test_a_failed_listing_is_a_problem_not_an_error() -> None:
    stub = CallerStub({"list_open_documents": {"documents": []}})
    guard = DocumentGuard(stub)

    async with guard:
        folder = guard.folder
        stub.failures["list_open_documents"] = "SolidWorks is busy"

    assert guard.problems == ["could not list the open documents: SolidWorks is busy"]
    assert not folder.exists()


def test_the_folder_is_only_there_inside_async_with() -> None:
    with pytest.raises(RuntimeError, match="outside `async with`"):
        _ = DocumentGuard(CallerStub()).folder
