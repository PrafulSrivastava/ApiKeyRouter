"""Tests for RoutingDecision data model."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from apikeyrouter.domain.models.routing_decision import (
    AlternativeRoute,
    ObjectiveType,
    RoutingDecision,
    RoutingObjective,
)


class TestObjectiveType:
    """Tests for ObjectiveType enum."""

    def test_objective_type_enum_values(self) -> None:
        """Test that all ObjectiveType enum values are defined."""
        assert ObjectiveType.Cost == "cost"
        assert ObjectiveType.Reliability == "reliability"
        assert ObjectiveType.Fairness == "fairness"
        assert ObjectiveType.Quality == "quality"

    def test_objective_type_enum_membership(self) -> None:
        """Test ObjectiveType enum membership."""
        values = [obj.value for obj in ObjectiveType]
        assert "cost" in values
        assert "reliability" in values
        assert "fairness" in values
        assert "quality" in values


class TestRoutingObjective:
    """Tests for RoutingObjective model."""

    def test_routing_objective_creation_with_minimal_fields(self) -> None:
        """Test RoutingObjective creation with only required fields."""
        objective = RoutingObjective(primary="cost")

        assert objective.primary == "cost"
        assert objective.secondary == []
        assert objective.constraints == {}
        assert objective.weights == {}

    def test_routing_objective_creation_with_all_fields(self) -> None:
        """Test RoutingObjective creation with all fields."""
        objective = RoutingObjective(
            primary="cost",
            secondary=["reliability", "quality"],
            constraints={"max_cost": 0.01, "min_reliability": 0.95},
            weights={"cost": 0.7, "reliability": 0.3},
        )

        assert objective.primary == "cost"
        assert objective.secondary == ["reliability", "quality"]
        assert objective.constraints == {"max_cost": 0.01, "min_reliability": 0.95}
        assert objective.weights == {"cost": 0.7, "reliability": 0.3}

    def test_routing_objective_primary_validation(self) -> None:
        """Test RoutingObjective primary field validation."""
        # Valid primary objectives
        for obj_type in ObjectiveType:
            objective = RoutingObjective(primary=obj_type.value)
            assert objective.primary == obj_type.value

        # Latency is also valid (from architecture docs)
        objective = RoutingObjective(primary="latency")
        assert objective.primary == "latency"

        # Case insensitive
        objective = RoutingObjective(primary="COST")
        assert objective.primary == "cost"

        # Invalid primary objective
        with pytest.raises(ValueError, match="Primary objective must be one of"):
            RoutingObjective(primary="invalid_objective")

    def test_routing_objective_secondary_validation(self) -> None:
        """Test RoutingObjective secondary field validation."""
        # Valid secondary objectives
        objective = RoutingObjective(
            primary="cost",
            secondary=["reliability", "quality", "fairness"],
        )
        assert objective.secondary == ["reliability", "quality", "fairness"]

        # Case insensitive
        objective = RoutingObjective(primary="cost", secondary=["RELIABILITY", "Quality"])
        assert objective.secondary == ["reliability", "quality"]

        # Invalid secondary objective
        with pytest.raises(ValueError, match="Secondary objective must be one of"):
            RoutingObjective(primary="cost", secondary=["invalid_objective"])

    def test_routing_objective_weights_validation(self) -> None:
        """Test RoutingObjective weights validation."""
        # Valid weights
        objective = RoutingObjective(
            primary="cost",
            weights={"cost": 0.5, "reliability": 0.5},
        )
        assert objective.weights == {"cost": 0.5, "reliability": 0.5}

        # Weight at boundary (0.0)
        objective = RoutingObjective(primary="cost", weights={"cost": 0.0})
        assert objective.weights == {"cost": 0.0}

        # Weight at boundary (1.0)
        objective = RoutingObjective(primary="cost", weights={"cost": 1.0})
        assert objective.weights == {"cost": 1.0}

        # Weight below 0.0 should raise error
        with pytest.raises(ValueError, match="Weight for .* must be between 0.0 and 1.0"):
            RoutingObjective(primary="cost", weights={"cost": -0.1})

        # Weight above 1.0 should raise error
        with pytest.raises(ValueError, match="Weight for .* must be between 0.0 and 1.0"):
            RoutingObjective(primary="cost", weights={"cost": 1.1})


class TestAlternativeRoute:
    """Tests for AlternativeRoute model."""

    def test_alternative_route_creation_with_minimal_fields(self) -> None:
        """Test AlternativeRoute creation with only required fields."""
        alt_route = AlternativeRoute(
            key_id="key_1",
            provider_id="openai",
        )

        assert alt_route.key_id == "key_1"
        assert alt_route.provider_id == "openai"
        assert alt_route.score is None
        assert alt_route.reason_not_selected is None

    def test_alternative_route_creation_with_all_fields(self) -> None:
        """Test AlternativeRoute creation with all fields."""
        alt_route = AlternativeRoute(
            key_id="key_1",
            provider_id="openai",
            score=0.85,
            reason_not_selected="Lower confidence score",
        )

        assert alt_route.key_id == "key_1"
        assert alt_route.provider_id == "openai"
        assert alt_route.score == 0.85
        assert alt_route.reason_not_selected == "Lower confidence score"


class TestRoutingDecision:
    """Tests for RoutingDecision model."""

    def test_routing_decision_creation_with_minimal_fields(self) -> None:
        """Test RoutingDecision creation with only required fields."""
        objective = RoutingObjective(primary="cost")
        decision = RoutingDecision(
            id="decision_1",
            request_id="request_1",
            selected_key_id="key_1",
            selected_provider_id="openai",
            objective=objective,
            explanation="Selected key with lowest cost",
            confidence=0.9,
        )

        assert decision.id == "decision_1"
        assert decision.request_id == "request_1"
        assert decision.selected_key_id == "key_1"
        assert decision.selected_provider_id == "openai"
        assert decision.objective == objective
        assert decision.explanation == "Selected key with lowest cost"
        assert decision.confidence == 0.9
        assert decision.eligible_keys == []
        assert decision.evaluation_results == {}
        assert decision.alternatives_considered == []
        assert isinstance(decision.decision_timestamp, datetime)

    def test_routing_decision_creation_with_all_fields(self) -> None:
        """Test RoutingDecision creation with all fields."""
        timestamp = datetime.utcnow()
        objective = RoutingObjective(
            primary="cost",
            secondary=["reliability"],
            weights={"cost": 0.7, "reliability": 0.3},
        )
        alt_route = AlternativeRoute(
            key_id="key_2",
            provider_id="anthropic",
            score=0.75,
            reason_not_selected="Higher cost",
        )

        decision = RoutingDecision(
            id="decision_2",
            request_id="request_2",
            selected_key_id="key_1",
            selected_provider_id="openai",
            decision_timestamp=timestamp,
            objective=objective,
            eligible_keys=["key_1", "key_2", "key_3"],
            evaluation_results={
                "key_1": {"cost": 0.01, "reliability": 0.95, "total_score": 0.9},
                "key_2": {"cost": 0.02, "reliability": 0.98, "total_score": 0.75},
                "key_3": {"cost": 0.015, "reliability": 0.92, "total_score": 0.8},
            },
            explanation="Selected key_1 as it had the lowest cost while maintaining acceptable reliability",
            confidence=0.92,
            alternatives_considered=[alt_route],
        )

        assert decision.id == "decision_2"
        assert decision.request_id == "request_2"
        assert decision.selected_key_id == "key_1"
        assert decision.selected_provider_id == "openai"
        assert decision.decision_timestamp == timestamp
        assert decision.objective == objective
        assert decision.eligible_keys == ["key_1", "key_2", "key_3"]
        assert len(decision.evaluation_results) == 3
        assert (
            decision.explanation
            == "Selected key_1 as it had the lowest cost while maintaining acceptable reliability"
        )
        assert decision.confidence == 0.92
        assert len(decision.alternatives_considered) == 1
        assert decision.alternatives_considered[0] == alt_route

    def test_routing_decision_id_validation(self) -> None:
        """Test RoutingDecision ID validation."""
        objective = RoutingObjective(primary="cost")

        # Valid ID
        decision = RoutingDecision(
            id="valid-decision-id",
            request_id="request_1",
            selected_key_id="key_1",
            selected_provider_id="openai",
            objective=objective,
            explanation="Test explanation",
            confidence=0.9,
        )
        assert decision.id == "valid-decision-id"

        # Empty ID should raise error
        with pytest.raises(ValidationError):
            RoutingDecision(
                id="",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=0.9,
            )

        # Whitespace-only ID should be stripped and then raise error
        with pytest.raises(ValidationError):
            RoutingDecision(
                id="   ",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=0.9,
            )

        # ID too long should raise error
        long_id = "a" * 256
        with pytest.raises(ValueError, match="Decision ID must be 255 characters or less"):
            RoutingDecision(
                id=long_id,
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=0.9,
            )

    def test_routing_decision_request_id_validation(self) -> None:
        """Test RoutingDecision request_id validation."""
        objective = RoutingObjective(primary="cost")

        # Valid request ID
        decision = RoutingDecision(
            id="decision_1",
            request_id="valid-request-id",
            selected_key_id="key_1",
            selected_provider_id="openai",
            objective=objective,
            explanation="Test explanation",
            confidence=0.9,
        )
        assert decision.request_id == "valid-request-id"

        # Empty request ID should raise error
        with pytest.raises(ValidationError):
            RoutingDecision(
                id="decision_1",
                request_id="",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=0.9,
            )

    def test_routing_decision_explanation_validation(self) -> None:
        """Test RoutingDecision explanation validation (critical rule)."""
        objective = RoutingObjective(primary="cost")

        # Valid explanation
        decision = RoutingDecision(
            id="decision_1",
            request_id="request_1",
            selected_key_id="key_1",
            selected_provider_id="openai",
            objective=objective,
            explanation="Valid explanation",
            confidence=0.9,
        )
        assert decision.explanation == "Valid explanation"

        # Empty explanation should raise error (critical rule)
        # Pydantic's min_length validation runs first, so we check for that message
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            RoutingDecision(
                id="decision_1",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="",
                confidence=0.9,
            )

        # Whitespace-only explanation should raise error
        # str_strip_whitespace=True strips whitespace before validation, so it becomes empty
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            RoutingDecision(
                id="decision_1",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="   ",
                confidence=0.9,
            )

    def test_routing_decision_confidence_validation(self) -> None:
        """Test RoutingDecision confidence validation."""
        objective = RoutingObjective(primary="cost")

        # Valid confidence values
        for conf in [0.0, 0.5, 1.0]:
            decision = RoutingDecision(
                id="decision_1",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=conf,
            )
            assert decision.confidence == conf

        # Confidence below 0.0 should raise error
        with pytest.raises(ValidationError):
            RoutingDecision(
                id="decision_1",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=-0.1,
            )

        # Confidence above 1.0 should raise error
        with pytest.raises(ValidationError):
            RoutingDecision(
                id="decision_1",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation="Test explanation",
                confidence=1.1,
            )

    def test_routing_decision_evaluation_results_structure(self) -> None:
        """Test RoutingDecision evaluation_results dict structure."""
        objective = RoutingObjective(primary="cost")

        # Evaluation results with various structures
        decision = RoutingDecision(
            id="decision_1",
            request_id="request_1",
            selected_key_id="key_1",
            selected_provider_id="openai",
            objective=objective,
            explanation="Test explanation",
            confidence=0.9,
            evaluation_results={
                "key_1": {"cost": 0.01, "reliability": 0.95},
                "key_2": {"cost": 0.02, "reliability": 0.98, "metadata": {"tier": "premium"}},
                "key_3": {"score": 0.8},
            },
        )

        assert "key_1" in decision.evaluation_results
        assert "key_2" in decision.evaluation_results
        assert "key_3" in decision.evaluation_results
        assert decision.evaluation_results["key_1"]["cost"] == 0.01
        assert decision.evaluation_results["key_2"]["metadata"]["tier"] == "premium"

    def test_routing_decision_alternatives_considered(self) -> None:
        """Test RoutingDecision alternatives_considered field."""
        objective = RoutingObjective(primary="cost")
        alt_routes = [
            AlternativeRoute(
                key_id="key_2",
                provider_id="anthropic",
                score=0.75,
                reason_not_selected="Higher cost",
            ),
            AlternativeRoute(
                key_id="key_3",
                provider_id="openai",
                score=0.8,
                reason_not_selected="Lower reliability",
            ),
        ]

        decision = RoutingDecision(
            id="decision_1",
            request_id="request_1",
            selected_key_id="key_1",
            selected_provider_id="openai",
            objective=objective,
            explanation="Test explanation",
            confidence=0.9,
            alternatives_considered=alt_routes,
        )

        assert len(decision.alternatives_considered) == 2
        assert decision.alternatives_considered[0].key_id == "key_2"
        assert decision.alternatives_considered[1].key_id == "key_3"

    def test_routing_decision_all_objective_types(self) -> None:
        """Test RoutingDecision with all objective types."""
        objective = RoutingObjective(primary="cost")

        for obj_type in ObjectiveType:
            objective = RoutingObjective(primary=obj_type.value)
            decision = RoutingDecision(
                id=f"decision_{obj_type.value}",
                request_id="request_1",
                selected_key_id="key_1",
                selected_provider_id="openai",
                objective=objective,
                explanation=f"Selected based on {obj_type.value}",
                confidence=0.9,
            )
            assert decision.objective.primary == obj_type.value
