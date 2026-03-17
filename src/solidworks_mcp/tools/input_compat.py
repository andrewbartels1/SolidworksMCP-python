"""Shared input model compatibility helpers for tool schemas.

This module centralizes test/backward-compat parsing behavior so individual
tool modules stay focused on domain fields.
"""

from pydantic import BaseModel, ConfigDict


class CompatInput(BaseModel):
    """Base schema allowing legacy/extra fields used by existing tests."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
