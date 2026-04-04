"""Tests for src/solidworks_mcp/agents/schemas.py — targeting 100% coverage."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.solidworks_mcp.agents.schemas import (
    Assumption,
    DocsPlan,
    ManufacturabilityReview,
    RecoverableFailure,
    Recommendation,
    ToolRoutingDecision,
)


# ---------------------------------------------------------------------------
# Assumption
# ---------------------------------------------------------------------------


class TestAssumption:
    def test_valid(self):
        a = Assumption(statement="Material is PLA.")
        assert a.statement == "Material is PLA."

    def test_statement_too_short(self):
        with pytest.raises(ValidationError):
            Assumption(statement="ab")  # min_length=3

    def test_statement_exactly_min_length(self):
        a = Assumption(statement="abc")
        assert len(a.statement) == 3


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


class TestRecommendation:
    def test_valid_low_risk(self):
        r = Recommendation(title="Add chamfer", rationale="Reduces stress", risk="low")
        assert r.risk == "low"

    def test_valid_medium_risk(self):
        r = Recommendation(title="Check wall", rationale="Walls may be thin", risk="medium")
        assert r.risk == "medium"

    def test_valid_high_risk(self):
        r = Recommendation(title="Redesign snap", rationale="Will fracture on PLA", risk="high")
        assert r.risk == "high"

    def test_invalid_risk_value(self):
        with pytest.raises(ValidationError):
            Recommendation(title="Test", rationale="Some reason here", risk="critical")

    def test_title_too_short(self):
        with pytest.raises(ValidationError):
            Recommendation(title="ab", rationale="Some reason", risk="low")

    def test_rationale_too_short(self):
        with pytest.raises(ValidationError):
            Recommendation(title="Valid title", rationale="No", risk="low")

    def test_serialization(self):
        r = Recommendation(title="Add fillet", rationale="Stress concentrations", risk="high")
        d = r.model_dump()
        assert d["risk"] == "high"
        assert d["title"] == "Add fillet"


# ---------------------------------------------------------------------------
# ManufacturabilityReview
# ---------------------------------------------------------------------------


class TestManufacturabilityReview:
    def _valid_review(self, **overrides):
        defaults = dict(
            summary="A ten-character summary.",
            orientation_guidance="Print flat side down.",
            build_volume_check="Fits in 220x220x250 envelope.",
        )
        defaults.update(overrides)
        return ManufacturabilityReview(**defaults)

    def test_minimal_valid(self):
        r = self._valid_review()
        assert r.assumptions == []
        assert r.recommendations == []
        assert r.tolerance_clearance_notes == []

    def test_with_assumptions_and_recommendations(self):
        r = self._valid_review(
            assumptions=[Assumption(statement="PLA material assumed.")],
            recommendations=[
                Recommendation(title="Thicken walls", rationale="Below 1.2 mm", risk="medium")
            ],
            tolerance_clearance_notes=["0.3-0.5 mm snap clearance"],
        )
        assert len(r.assumptions) == 1
        assert len(r.recommendations) == 1
        assert r.tolerance_clearance_notes[0].startswith("0.3")

    def test_summary_too_short(self):
        with pytest.raises(ValidationError):
            self._valid_review(summary="Short")  # min_length=10

    def test_orientation_guidance_too_short(self):
        with pytest.raises(ValidationError):
            self._valid_review(orientation_guidance="Bed")  # min_length=5

    def test_build_volume_check_too_short(self):
        with pytest.raises(ValidationError):
            self._valid_review(build_volume_check="OK")  # min_length=5

    def test_round_trip_json(self):
        r = self._valid_review(
            tolerance_clearance_notes=["0.3 mm clearance"],
        )
        json_str = r.model_dump_json()
        r2 = ManufacturabilityReview.model_validate_json(json_str)
        assert r2.summary == r.summary

    def test_nested_recommendation_invalid_risk_propagates(self):
        with pytest.raises(ValidationError):
            ManufacturabilityReview(
                summary="A valid summary here.",
                orientation_guidance="Print flat.",
                build_volume_check="Fits envelope.",
                recommendations=[{"title": "Fix", "rationale": "Because reasons", "risk": "extreme"}],
            )


# ---------------------------------------------------------------------------
# ToolRoutingDecision
# ---------------------------------------------------------------------------


class TestToolRoutingDecision:
    def test_valid_minimal(self):
        t = ToolRoutingDecision(
            intent="Create sketch",
            selected_tool_group="sketching_tools",
            why="Best match for geometry creation.",
        )
        assert t.fallback_strategy == []

    def test_with_fallback(self):
        t = ToolRoutingDecision(
            intent="Extrude part",
            selected_tool_group="modeling_tools",
            why="Extrude is the primary 3D tool.",
            fallback_strategy=["Use VBA if COM fails", "Check sketch closure"],
        )
        assert len(t.fallback_strategy) == 2

    def test_intent_too_short(self):
        with pytest.raises(ValidationError):
            ToolRoutingDecision(
                intent="ab",
                selected_tool_group="tools",
                why="Ten+ char reason.",
            )

    def test_selected_tool_group_too_short(self):
        with pytest.raises(ValidationError):
            ToolRoutingDecision(intent="Intent here", selected_tool_group="ab", why="Ten+ char why.")

    def test_why_too_short(self):
        with pytest.raises(ValidationError):
            ToolRoutingDecision(intent="Intent", selected_tool_group="tools", why="Short")


# ---------------------------------------------------------------------------
# DocsPlan
# ---------------------------------------------------------------------------


class TestDocsPlan:
    def test_minimal_valid(self):
        d = DocsPlan(
            audience="SolidWorks engineers",
            objective="Show bracket workflow.",
        )
        assert d.sections == []
        assert d.decisions == []
        assert d.demo_steps == []

    def test_with_all_fields(self):
        decision = ToolRoutingDecision(
            intent="Extrude",
            selected_tool_group="modeling",
            why="Core feature for 3D bodies.",
        )
        d = DocsPlan(
            audience="CAD beginners",
            objective="Teach sketch to extrusion.",
            sections=["Intro", "Setup", "Workflow"],
            decisions=[decision],
            demo_steps=["Open SolidWorks", "Create part", "Add sketch"],
        )
        assert len(d.sections) == 3
        assert len(d.decisions) == 1
        assert d.decisions[0].intent == "Extrude"

    def test_audience_too_short(self):
        with pytest.raises(ValidationError):
            DocsPlan(audience="ab", objective="Valid objective.")

    def test_objective_too_short(self):
        with pytest.raises(ValidationError):
            DocsPlan(audience="Engineers", objective="No")

    def test_serialization_includes_nested(self):
        d = DocsPlan(
            audience="Dev team",
            objective="Test serialization.",
            demo_steps=["Step one", "Step two"],
        )
        data = d.model_dump()
        assert data["demo_steps"] == ["Step one", "Step two"]


# ---------------------------------------------------------------------------
# RecoverableFailure
# ---------------------------------------------------------------------------


class TestRecoverableFailure:
    def test_default_should_retry_is_true(self):
        f = RecoverableFailure(explanation="Could not parse output schema.")
        assert f.should_retry is True
        assert f.retry_focus is None
        assert f.remediation_steps == []

    def test_should_retry_false(self):
        f = RecoverableFailure(
            explanation="Irreversible failure state.",
            should_retry=False,
        )
        assert f.should_retry is False

    def test_with_all_fields(self):
        f = RecoverableFailure(
            explanation="Schema validation failed on output.",
            remediation_steps=["Narrow the prompt", "Remove ambiguous constraints"],
            retry_focus="Focus on material constraints only.",
            should_retry=True,
        )
        assert len(f.remediation_steps) == 2
        assert f.retry_focus is not None

    def test_explanation_too_short(self):
        with pytest.raises(ValidationError):
            RecoverableFailure(explanation="Fail")  # min_length=8

    def test_round_trip_json(self):
        f = RecoverableFailure(
            explanation="Output did not match schema.",
            remediation_steps=["Use simpler prompt"],
        )
        json_str = f.model_dump_json()
        f2 = RecoverableFailure.model_validate_json(json_str)
        assert f2.explanation == f.explanation
        assert f2.remediation_steps == f.remediation_steps
