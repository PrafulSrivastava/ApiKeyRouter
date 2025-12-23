"""Tests for QuotaState data model."""

from datetime import datetime, timedelta

import pytest

from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    QuotaState,
    TimeWindow,
)


class TestCapacityState:
    """Tests for CapacityState enum."""

    def test_capacity_state_enum_values(self) -> None:
        """Test that all CapacityState enum values are defined."""
        assert CapacityState.Abundant == "abundant"
        assert CapacityState.Constrained == "constrained"
        assert CapacityState.Critical == "critical"
        assert CapacityState.Exhausted == "exhausted"
        assert CapacityState.Recovering == "recovering"

    def test_capacity_state_enum_membership(self) -> None:
        """Test CapacityState enum membership."""
        values = [state.value for state in CapacityState]
        assert "abundant" in values
        assert "constrained" in values
        assert "critical" in values
        assert "exhausted" in values
        assert "recovering" in values


class TestTimeWindow:
    """Tests for TimeWindow enum."""

    def test_time_window_enum_values(self) -> None:
        """Test that all TimeWindow enum values are defined."""
        assert TimeWindow.Daily == "daily"
        assert TimeWindow.Hourly == "hourly"
        assert TimeWindow.Monthly == "monthly"
        assert TimeWindow.Custom == "custom"

    def test_time_window_enum_membership(self) -> None:
        """Test TimeWindow enum membership."""
        values = [window.value for window in TimeWindow]
        assert "daily" in values
        assert "hourly" in values
        assert "monthly" in values
        assert "custom" in values

    def test_calculate_next_reset_hourly(self) -> None:
        """Test hourly reset calculation."""
        current = datetime(2024, 1, 15, 14, 30, 45)
        next_reset = TimeWindow.Hourly.calculate_next_reset(current)
        expected = datetime(2024, 1, 15, 15, 0, 0)
        assert next_reset == expected

    def test_calculate_next_reset_daily(self) -> None:
        """Test daily reset calculation."""
        current = datetime(2024, 1, 15, 14, 30, 45)
        next_reset = TimeWindow.Daily.calculate_next_reset(current)
        expected = datetime(2024, 1, 16, 0, 0, 0)
        assert next_reset == expected

    def test_calculate_next_reset_monthly(self) -> None:
        """Test monthly reset calculation."""
        current = datetime(2024, 1, 15, 14, 30, 45)
        next_reset = TimeWindow.Monthly.calculate_next_reset(current)
        expected = datetime(2024, 2, 1, 0, 0, 0)
        assert next_reset == expected

    def test_calculate_next_reset_monthly_december(self) -> None:
        """Test monthly reset calculation for December."""
        current = datetime(2024, 12, 15, 14, 30, 45)
        next_reset = TimeWindow.Monthly.calculate_next_reset(current)
        expected = datetime(2025, 1, 1, 0, 0, 0)
        assert next_reset == expected

    def test_calculate_next_reset_custom_raises_error(self) -> None:
        """Test that Custom time window raises error for reset calculation."""
        current = datetime(2024, 1, 15, 14, 30, 45)
        with pytest.raises(ValueError, match="Cannot calculate reset for Custom"):
            TimeWindow.Custom.calculate_next_reset(current)


class TestCapacityEstimate:
    """Tests for CapacityEstimate model."""

    def test_capacity_estimate_exact(self) -> None:
        """Test CapacityEstimate with exact value."""
        estimate = CapacityEstimate(value=100, confidence=1.0)
        assert estimate.value == 100
        assert estimate.min_value is None
        assert estimate.max_value is None
        assert estimate.confidence == 1.0
        assert estimate.get_estimate_type() == "exact"

    def test_capacity_estimate_estimated(self) -> None:
        """Test CapacityEstimate with estimated range."""
        estimate = CapacityEstimate(
            min_value=80, max_value=120, confidence=0.8, estimation_method="historical"
        )
        assert estimate.value is None
        assert estimate.min_value == 80
        assert estimate.max_value == 120
        assert estimate.confidence == 0.8
        assert estimate.estimation_method == "historical"
        assert estimate.get_estimate_type() == "estimated"

    def test_capacity_estimate_bounded_min(self) -> None:
        """Test CapacityEstimate with only min bound."""
        estimate = CapacityEstimate(min_value=50, confidence=0.6)
        assert estimate.value is None
        assert estimate.min_value == 50
        assert estimate.max_value is None
        assert estimate.get_estimate_type() == "bounded"

    def test_capacity_estimate_bounded_max(self) -> None:
        """Test CapacityEstimate with only max bound."""
        estimate = CapacityEstimate(max_value=200, confidence=0.6)
        assert estimate.value is None
        assert estimate.min_value is None
        assert estimate.max_value == 200
        assert estimate.get_estimate_type() == "bounded"

    def test_capacity_estimate_unknown(self) -> None:
        """Test CapacityEstimate with no information."""
        estimate = CapacityEstimate(confidence=0.0)
        assert estimate.value is None
        assert estimate.min_value is None
        assert estimate.max_value is None
        assert estimate.confidence == 0.0
        assert estimate.get_estimate_type() == "unknown"

    def test_capacity_estimate_with_verification(self) -> None:
        """Test CapacityEstimate with last_verified timestamp."""
        verified_at = datetime.utcnow()
        estimate = CapacityEstimate(value=100, confidence=0.9, last_verified=verified_at)
        assert estimate.value == 100
        assert estimate.last_verified == verified_at

    def test_capacity_estimate_value_validation(self) -> None:
        """Test CapacityEstimate value validation."""
        # Valid value
        estimate = CapacityEstimate(value=100)
        assert estimate.value == 100

        # Negative value should raise ValidationError (Pydantic Field validation)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CapacityEstimate(value=-1)

    def test_capacity_estimate_bounds_validation(self) -> None:
        """Test CapacityEstimate bounds validation."""
        # Valid bounds
        estimate = CapacityEstimate(min_value=50, max_value=100)
        assert estimate.min_value == 50
        assert estimate.max_value == 100

        # Negative min_value should raise ValidationError (Pydantic Field validation)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CapacityEstimate(min_value=-1, max_value=100)

        # Negative max_value should raise ValidationError (Pydantic Field validation)
        with pytest.raises(ValidationError):
            CapacityEstimate(min_value=50, max_value=-1)

    def test_capacity_estimate_confidence_validation(self) -> None:
        """Test CapacityEstimate confidence validation."""
        # Valid confidence
        estimate = CapacityEstimate(value=100, confidence=0.5)
        assert estimate.confidence == 0.5

        # Confidence > 1.0 should raise error
        with pytest.raises(ValueError):
            CapacityEstimate(value=100, confidence=1.5)

        # Confidence < 0.0 should raise error
        with pytest.raises(ValueError):
            CapacityEstimate(value=100, confidence=-0.1)

    def test_capacity_estimate_repr_exact(self) -> None:
        """Test CapacityEstimate __repr__ for exact estimate."""
        estimate = CapacityEstimate(value=100, confidence=0.9)
        repr_str = repr(estimate)
        assert "value=100" in repr_str
        assert "confidence=0.9" in repr_str

    def test_capacity_estimate_repr_estimated(self) -> None:
        """Test CapacityEstimate __repr__ for estimated range."""
        estimate = CapacityEstimate(min_value=80, max_value=120, confidence=0.8)
        repr_str = repr(estimate)
        assert "min=80" in repr_str
        assert "max=120" in repr_str
        assert "confidence=0.8" in repr_str

    def test_capacity_estimate_repr_bounded(self) -> None:
        """Test CapacityEstimate __repr__ for bounded estimate."""
        estimate = CapacityEstimate(min_value=50, confidence=0.6)
        repr_str = repr(estimate)
        assert "min=50" in repr_str
        assert "confidence=0.6" in repr_str


class TestQuotaState:
    """Tests for QuotaState model."""

    def test_quota_state_creation_with_minimal_fields(self) -> None:
        """Test QuotaState creation with only required fields."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            remaining_capacity=remaining,
            reset_at=reset_at,
        )

        assert quota.id == "quota_1"
        assert quota.key_id == "key_1"
        assert quota.capacity_state == CapacityState.Abundant
        assert quota.remaining_capacity == remaining
        assert quota.total_capacity is None
        assert quota.used_capacity == 0
        assert quota.time_window == TimeWindow.Daily
        assert quota.reset_at == reset_at
        assert isinstance(quota.updated_at, datetime)

    def test_quota_state_creation_with_all_fields(self) -> None:
        """Test QuotaState creation with all fields."""
        now = datetime.utcnow()
        reset_at = now + timedelta(hours=1)
        remaining = CapacityEstimate(value=50, confidence=0.9)
        quota = QuotaState(
            id="quota_2",
            key_id="key_2",
            capacity_state=CapacityState.Constrained,
            remaining_capacity=remaining,
            total_capacity=100,
            used_capacity=50,
            time_window=TimeWindow.Hourly,
            reset_at=reset_at,
            updated_at=now,
        )

        assert quota.id == "quota_2"
        assert quota.key_id == "key_2"
        assert quota.capacity_state == CapacityState.Constrained
        assert quota.remaining_capacity == remaining
        assert quota.total_capacity == 100
        assert quota.used_capacity == 50
        assert quota.time_window == TimeWindow.Hourly
        assert quota.reset_at == reset_at
        assert quota.updated_at == now

    def test_quota_state_default_values(self) -> None:
        """Test that QuotaState has correct default values."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)
        quota = QuotaState(
            id="quota_3",
            key_id="key_3",
            remaining_capacity=remaining,
            reset_at=reset_at,
        )

        assert quota.capacity_state == CapacityState.Abundant
        assert quota.total_capacity is None
        assert quota.used_capacity == 0
        assert quota.time_window == TimeWindow.Daily
        assert isinstance(quota.updated_at, datetime)

    def test_quota_state_id_validation(self) -> None:
        """Test QuotaState ID validation."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)

        # Valid ID
        quota = QuotaState(
            id="valid-quota-id", key_id="key_1", remaining_capacity=remaining, reset_at=reset_at
        )
        assert quota.id == "valid-quota-id"

        # Empty ID should raise error
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QuotaState(
                id="",
                key_id="key_1",
                remaining_capacity=remaining,
                reset_at=reset_at,
            )

        # Whitespace-only ID should be stripped and then raise error
        with pytest.raises(ValidationError):
            QuotaState(
                id="   ",
                key_id="key_1",
                remaining_capacity=remaining,
                reset_at=reset_at,
            )

        # ID too long should raise error
        long_id = "a" * 256
        with pytest.raises(ValueError, match="ID must be 255 characters or less"):
            QuotaState(
                id=long_id,
                key_id="key_1",
                remaining_capacity=remaining,
                reset_at=reset_at,
            )

    def test_quota_state_key_id_validation(self) -> None:
        """Test QuotaState key_id validation."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)

        # Valid key_id
        quota = QuotaState(
            id="quota_1", key_id="valid-key-id", remaining_capacity=remaining, reset_at=reset_at
        )
        assert quota.key_id == "valid-key-id"

        # Empty key_id should raise error
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QuotaState(
                id="quota_1",
                key_id="",
                remaining_capacity=remaining,
                reset_at=reset_at,
            )

        # Key ID too long should raise error
        long_key_id = "a" * 256
        with pytest.raises(ValueError, match="ID must be 255 characters or less"):
            QuotaState(
                id="quota_1",
                key_id=long_key_id,
                remaining_capacity=remaining,
                reset_at=reset_at,
            )

    def test_quota_state_used_capacity_validation(self) -> None:
        """Test QuotaState used_capacity validation."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)

        # Valid used capacity
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            remaining_capacity=remaining,
            reset_at=reset_at,
            used_capacity=50,
        )
        assert quota.used_capacity == 50

        # Negative used capacity should raise ValidationError (Pydantic Field validation)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QuotaState(
                id="quota_1",
                key_id="key_1",
                remaining_capacity=remaining,
                reset_at=reset_at,
                used_capacity=-1,
            )

    def test_quota_state_total_capacity_validation(self) -> None:
        """Test QuotaState total_capacity validation."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)

        # Valid total capacity
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            remaining_capacity=remaining,
            reset_at=reset_at,
            total_capacity=200,
        )
        assert quota.total_capacity == 200

        # None is valid
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            remaining_capacity=remaining,
            reset_at=reset_at,
            total_capacity=None,
        )
        assert quota.total_capacity is None

        # Negative total capacity should raise ValidationError (Pydantic Field validation)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QuotaState(
                id="quota_1",
                key_id="key_1",
                remaining_capacity=remaining,
                reset_at=reset_at,
                total_capacity=-1,
            )

    def test_quota_state_all_capacity_states(self) -> None:
        """Test QuotaState with all possible capacity states."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)
        states = [
            CapacityState.Abundant,
            CapacityState.Constrained,
            CapacityState.Critical,
            CapacityState.Exhausted,
            CapacityState.Recovering,
        ]

        for state in states:
            quota = QuotaState(
                id=f"quota_{state.value}",
                key_id="key_1",
                capacity_state=state,
                remaining_capacity=remaining,
                reset_at=reset_at,
            )
            assert quota.capacity_state == state

    def test_quota_state_all_time_windows(self) -> None:
        """Test QuotaState with all possible time windows."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)
        windows = [
            TimeWindow.Hourly,
            TimeWindow.Daily,
            TimeWindow.Monthly,
            TimeWindow.Custom,
        ]

        for window in windows:
            quota = QuotaState(
                id=f"quota_{window.value}",
                key_id="key_1",
                remaining_capacity=remaining,
                time_window=window,
                reset_at=reset_at,
            )
            assert quota.time_window == window

    def test_quota_state_repr(self) -> None:
        """Test QuotaState __repr__."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(value=100)
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            capacity_state=CapacityState.Constrained,
            remaining_capacity=remaining,
            used_capacity=50,
            time_window=TimeWindow.Hourly,
            reset_at=reset_at,
        )

        repr_str = repr(quota)
        assert "quota_1" in repr_str
        assert "key_1" in repr_str
        assert "constrained" in repr_str
        assert "50" in repr_str
        assert "hourly" in repr_str

    def test_quota_state_with_estimated_capacity(self) -> None:
        """Test QuotaState with estimated capacity (not exact)."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(
            min_value=80, max_value=120, confidence=0.8, estimation_method="historical"
        )
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            remaining_capacity=remaining,
            reset_at=reset_at,
        )

        assert quota.remaining_capacity.get_estimate_type() == "estimated"
        assert quota.remaining_capacity.min_value == 80
        assert quota.remaining_capacity.max_value == 120

    def test_quota_state_with_unknown_capacity(self) -> None:
        """Test QuotaState with unknown capacity."""
        reset_at = datetime.utcnow() + timedelta(hours=1)
        remaining = CapacityEstimate(confidence=0.0)
        quota = QuotaState(
            id="quota_1",
            key_id="key_1",
            remaining_capacity=remaining,
            reset_at=reset_at,
        )

        assert quota.remaining_capacity.get_estimate_type() == "unknown"
        assert quota.remaining_capacity.value is None
        assert quota.remaining_capacity.min_value is None
        assert quota.remaining_capacity.max_value is None
