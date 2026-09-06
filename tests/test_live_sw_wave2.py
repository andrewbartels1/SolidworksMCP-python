"""Real-SolidWorks regression tests for the Wave 2 tool additions.

Covers ``set_units`` (#60), ``rename_feature`` (#59), ``list_open_documents``
/ ``activate_document`` (#61), and the shared ``_sync_current_model_from_active``
resync those tools depend on - the issue #91 follow-on where a tool that reads
``adapter.currentModel`` first has to recover it from ``ISldWorks::ActiveDoc``,
or it reports "No active model" for documents the user opened in the
SolidWorks UI rather than through a tool.

Gating matches ``tests/test_live_sw_regression.py``:
  - ``@pytest.mark.solidworks_only`` / ``@pytest.mark.windows_only``
  - skipped unless ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1``

Unlike the older real-integration tests, cleanup here closes only the
scratch documents each test created (never ``CloseAllDocuments``), so the
suite is safe to run against a SolidWorks session that has real work open.

Run locally on Windows with SolidWorks open::

    SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1 \
        python -m pytest tests/test_live_sw_wave2.py -v
"""

from __future__ import annotations

import os
import platform
from collections.abc import AsyncIterator

import pytest

_REAL_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"
_REAL_ENABLED = os.getenv(_REAL_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}

pytestmark = [
    pytest.mark.solidworks_only,
    pytest.mark.windows_only,
    pytest.mark.skipif(
        not _REAL_ENABLED,
        reason=f"set {_REAL_FLAG}=1 to run tests that require a live SolidWorks install",
    ),
    pytest.mark.skipif(
        platform.system() != "Windows",
        reason="SolidWorks only runs on Windows",
    ),
]


class _ScratchSession:
    """A connected adapter plus cleanup of only the scratch docs a test made.

    Cleanup closes a document only when **both** guards agree it is scratch:

    * its title is not in the snapshot taken when the session was created, and
    * ``GetPathName`` is empty - i.e. it has never been saved.

    A real file the user already had open always has a path, so it can never
    be closed here even if the baseline snapshot comes back empty.
    """

    def __init__(self, adapter) -> None:  # noqa: ANN001
        self.adapter = adapter
        self._baseline: set[str] = self._open_titles()

    def _open_docs(self) -> list:
        raw = self.adapter._attempt(
            lambda: self.adapter.swApp.GetDocuments(), default=None
        )
        if isinstance(raw, (list, tuple)):
            return [d for d in raw if d is not None]
        return [raw] if raw else []

    def _open_titles(self) -> set[str]:
        titles: set[str] = set()
        for d in self._open_docs():
            t = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            if t:
                titles.add(str(t))
        return titles

    def cleanup(self) -> None:
        for d in self._open_docs():
            title = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            path = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetPathName"),
                default=None,
            )
            if not title or str(title) in self._baseline:
                continue
            if path:  # saved file — never ours to close
                continue
            self.adapter._attempt(
                lambda t=str(title): self.adapter.swApp.CloseDoc(t)
            )


@pytest.fixture
async def scratch() -> AsyncIterator[_ScratchSession]:
    """Yield a connected adapter; on teardown close only its scratch docs."""
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    adapter = PyWin32Adapter({})
    await adapter.connect()
    session = _ScratchSession(adapter)
    try:
        yield session
    finally:
        session.cleanup()
        await adapter.disconnect()


# ---- set_units (#60) -------------------------------------------------------


@pytest.mark.asyncio
async def test_set_units_round_trips_and_verifies_against_the_document(scratch):
    """set_units moves the document's real unit system and reads it back.

    Verification is against ``swUnitSystem`` (swconst slot 263) read straight
    off ``IModelDocExtension`` - not the preference slot the tool wrote - so a
    build that accepts the call but ignores it is caught. The enum integers
    are the non-obvious values transcribed from a live ``swconst.tlb``
    (263 / 47; swUnitSystem_e IPS=3, MMGS=5).
    """
    from solidworks_mcp.adapters.solidworks.io import (
        _SW_PREF_UNIT_SYSTEM,
        _SW_UNIT_SYSTEMS,
    )

    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success

    def _observed_system() -> int:
        ext = adapter.currentModel.Extension
        return int(ext.GetUserPreferenceInteger(_SW_PREF_UNIT_SYSTEM, 0))

    to_inches = await adapter.set_units("in")
    assert to_inches.is_success, to_inches.error
    assert to_inches.data["verified"] is True
    assert to_inches.data["observed_unit_system"] == _SW_UNIT_SYSTEMS["in"][0]
    assert _observed_system() == _SW_UNIT_SYSTEMS["in"][0]  # IPS

    to_mm = await adapter.set_units("Millimeters")  # alias must resolve
    assert to_mm.is_success, to_mm.error
    assert to_mm.data["verified"] is True
    assert _observed_system() == _SW_UNIT_SYSTEMS["mm"][0]  # MMGS


@pytest.mark.asyncio
async def test_set_units_rejects_an_unknown_token_without_touching_the_document(
    scratch,
):
    """An unrecognised unit token is an error, and the document is untouched."""
    from solidworks_mcp.adapters.solidworks.io import _SW_PREF_UNIT_SYSTEM

    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success

    def _system() -> int:
        return int(
            adapter.currentModel.Extension.GetUserPreferenceInteger(
                _SW_PREF_UNIT_SYSTEM, 0
            )
        )

    before = _system()
    bad = await adapter.set_units("furlongs")
    assert not bad.is_success
    assert "furlongs" in (bad.error or "")
    assert _system() == before


@pytest.mark.asyncio
async def test_set_units_recovers_when_current_model_is_stale(scratch):
    """A tool must resync from ActiveDoc, not trust a stale currentModel.

    Reproduces the "No active model" failure seen live: the user opened a
    document in the SolidWorks UI, so ``adapter.currentModel`` was never set
    by a tool. ``set_units`` (like ``get_model_info``) recovers by reading
    ``ISldWorks::ActiveDoc``.
    """
    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success
    adapter.currentModel = None  # SW still has a live ActiveDoc

    result = await adapter.set_units("in")
    assert result.is_success, result.error
    assert result.data["verified"] is True
    assert adapter.currentModel is not None


# ---- rename_feature (#59) ------------------------------------------------


@pytest.mark.asyncio
async def test_rename_feature_renames_and_reads_the_new_name_back(scratch):
    """rename_feature changes IFeature.Name and the feature re-resolves.

    ``IFeature::Name`` is a settable property (assigned, never called). The
    feature must resolve under the new name afterwards and not the old one.
    Also covers the two edge cases the tool promises to handle: a name
    collision is a hard error (SW silently refuses it), and renaming to the
    current name is a no-op success.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0.0, 0.0, 40.0, 25.0)
    await adapter.exit_sketch()
    created = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert created.is_success, created.error
    old_name = getattr(created.data, "name", None) or "Boss-Extrude1"

    renamed = await adapter.rename_feature(old_name, "RenamedByTest")
    assert renamed.is_success, renamed.error
    assert renamed.data["renamed"] is True
    assert renamed.data["new_name"] == "RenamedByTest"
    assert adapter.currentModel.FeatureByName("RenamedByTest") is not None
    assert adapter.currentModel.FeatureByName(old_name) is None

    clash = await adapter.rename_feature("Sketch1", "RenamedByTest")
    assert not clash.is_success
    assert "already exists" in (clash.error or "")

    noop = await adapter.rename_feature("RenamedByTest", "RenamedByTest")
    assert noop.is_success
    assert noop.data["renamed"] is False

    back = await adapter.rename_feature("RenamedByTest", old_name)
    assert back.is_success, back.error
    assert adapter.currentModel.FeatureByName(old_name) is not None


@pytest.mark.asyncio
async def test_rename_feature_unknown_feature_is_an_error(scratch):
    """Renaming a feature that does not exist must error, not fabricate."""
    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success
    bad = await adapter.rename_feature("NoSuchFeature", "Whatever")
    assert not bad.is_success
    assert "NoSuchFeature" in (bad.error or "")


# ---- list_open_documents / activate_document (#61) ---------------------


@pytest.mark.asyncio
async def test_list_open_documents_reports_the_active_part(scratch):
    """A freshly created part shows up in the enumeration, marked active."""
    adapter = scratch.adapter
    created = await adapter.create_part()
    assert created.is_success, created.error
    title = getattr(created.data, "name", None)

    listed = await adapter.list_open_documents()
    assert listed.is_success, listed.error
    assert isinstance(listed.data, list) and listed.data

    active = [d for d in listed.data if d["is_active"]]
    assert len(active) == 1, listed.data
    assert active[0]["type"] == "Part"
    if title:
        assert active[0]["title"] == title
    # Every entry has the documented shape.
    for entry in listed.data:
        assert set(entry) == {"title", "path", "type", "is_active"}


@pytest.mark.asyncio
async def test_activate_document_switches_the_active_document(scratch):
    """activate_document makes a named open document active and verifies it."""
    adapter = scratch.adapter
    first = await adapter.create_part()
    assert first.is_success, first.error
    first_title = getattr(first.data, "name", None)
    assert first_title

    second = await adapter.create_part()
    assert second.is_success, second.error
    second_title = getattr(second.data, "name", None)

    # The second part is active now; switch back to the first by title.
    switched = await adapter.activate_document(first_title)
    assert switched.is_success, switched.error
    assert switched.data["verified"] is True
    assert str(adapter.swApp.ActiveDoc.GetTitle) == first_title

    missing = await adapter.activate_document("definitely_not_open.SLDPRT")
    assert not missing.is_success
    assert "No open document matches" in (missing.error or "")
    if second_title:
        assert second_title in (missing.error or "")


# ---- shared ActiveDoc resync (issue #91 follow-on) --------------------


@pytest.mark.asyncio
async def test_get_model_info_resyncs_from_active_doc_without_a_tool_open(scratch):
    """get_model_info recovers a stale/absent currentModel from ActiveDoc.

    This is the shared ``_sync_current_model_from_active`` path that issue
    #91's fix introduced and Wave 2 factored out; regressing it brings back
    "No active model" for UI-opened documents.
    """
    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success
    adapter.currentModel = None

    info = await adapter.get_model_info()
    assert info.is_success, info.error
    assert info.data["type"] == "Part"
    assert adapter.currentModel is not None
