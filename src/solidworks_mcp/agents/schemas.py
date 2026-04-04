"""Typed output schemas for agent prompt validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Assumption(BaseModel):
    """A single explicit assumption in an agent response."""

    statement: str = Field(min_length=3)


class Recommendation(BaseModel):
    """A prioritized recommendation with rationale and risk."""

    title: str = Field(min_length=3)
    rationale: str = Field(min_length=5)
    risk: Literal["low", "medium", "high"]


class ManufacturabilityReview(BaseModel):
    """Validation shape for printability-focused agent responses."""

    summary: str = Field(min_length=10)
    assumptions: list[Assumption] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    orientation_guidance: str = Field(min_length=5)
    tolerance_clearance_notes: list[str] = Field(default_factory=list)
    build_volume_check: str = Field(
        description="Expected to state pass/fail and mitigation options when needed.",
        min_length=5,
    )


class ToolRoutingDecision(BaseModel):
    """Validation shape for tool-selection/skills documentation prompts."""

    intent: str = Field(min_length=3)
    selected_tool_group: str = Field(min_length=3)
    why: str = Field(min_length=10)
    fallback_strategy: list[str] = Field(default_factory=list)


class DocsPlan(BaseModel):
    """Validation shape for docs-engineering responses."""

    audience: str = Field(min_length=3)
    objective: str = Field(min_length=5)
    sections: list[str] = Field(default_factory=list)
    decisions: list[ToolRoutingDecision] = Field(default_factory=list)
    demo_steps: list[str] = Field(default_factory=list)


class FeatureStep(BaseModel):
    """One step in a part reconstruction plan."""

    step_number: int = Field(ge=1)
    tool_name: str = Field(min_length=2, description="MCP tool or action, e.g. create_extrusion")
    description: str = Field(min_length=5)
    mcp_call: str = Field(
        min_length=5,
        description="Python-style call string, e.g. create_extrusion(sketch_name='Sketch1', depth=10.0)",
    )


class ReconstructionPlan(BaseModel):
    """Structured plan for recreating a SolidWorks part from scratch using MCP tools."""

    part_name: str = Field(min_length=2)
    complexity_tier: Literal[1, 2, 3, 4] = Field(
        description="1=Simple revolve/extrude, 2=Multi-sketch, 3=VBA/loft, 4=Assembly"
    )
    analysis_summary: str = Field(
        min_length=10,
        description="Brief summary of the part's key geometry and design intent.",
    )
    feature_sequence: list[FeatureStep] = Field(
        min_length=1, description="Ordered list of MCP tool calls to recreate the part."
    )
    vba_required: bool = Field(
        description="True if any feature requires generate_vba_part_modeling + execute_macro."
    )
    assembly_mates: list[str] = Field(
        default_factory=list,
        description="Mate descriptions for assembly parts, e.g. 'coincident: shaft_axis to yoke_bore'.",
    )
    validation_strategy: str = Field(
        min_length=5,
        description="How to confirm the reconstruction matches the original (e.g. pixel diff, mass properties).",
    )


class RecoverableFailure(BaseModel):
    """Typed failure output used when agent needs user-guided retry."""

    explanation: str = Field(min_length=8)
    remediation_steps: list[str] = Field(default_factory=list)
    retry_focus: str | None = Field(
        default=None,
        description="Optional hint on what to change in the next prompt.",
    )
    should_retry: bool = True
