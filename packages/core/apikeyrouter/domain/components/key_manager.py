"""KeyManager component for API key lifecycle management."""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityManager,
)
from apikeyrouter.domain.interfaces.state_store import StateStore, StateStoreError
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.utils.encryption import (
    EncryptionError,
    EncryptionService,
    encrypt_key_material,  # Backward compatibility
)
from apikeyrouter.infrastructure.utils.validation import (
    ValidationError,
    validate_key_material,
    validate_metadata,
    validate_provider_id,
)


class KeyRegistrationError(Exception):
    """Raised when key registration fails."""

    pass


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class KeyNotFoundError(Exception):
    """Raised when a key is not found."""

    pass


class KeyManager:
    """Manages API key lifecycle, state transitions, and key selection eligibility.

    KeyManager ensures keys are individually addressable with stable identity
    and that key state is explicit and observable.
    """

    # Valid state transitions according to state machine
    _VALID_TRANSITIONS: dict[KeyState, set[KeyState]] = {
        KeyState.Available: {
            KeyState.Throttled,
            KeyState.Exhausted,
            KeyState.Disabled,
            KeyState.Invalid,
        },
        KeyState.Throttled: {KeyState.Available, KeyState.Disabled, KeyState.Invalid},
        KeyState.Exhausted: {
            KeyState.Recovering,
            KeyState.Disabled,
            KeyState.Invalid,
        },
        KeyState.Recovering: {
            KeyState.Available,
            KeyState.Exhausted,
            KeyState.Disabled,
            KeyState.Invalid,
        },
        KeyState.Disabled: {KeyState.Available, KeyState.Invalid},
        KeyState.Invalid: {KeyState.Disabled},  # Can only manually disable invalid keys
    }

    def __init__(
        self,
        state_store: StateStore,
        observability_manager: ObservabilityManager,
        default_cooldown_seconds: int = 60,
        encryption_service: EncryptionService | None = None,
    ) -> None:
        """Initialize KeyManager with dependencies.

        Args:
            state_store: StateStore implementation for persistence.
            observability_manager: ObservabilityManager for events and logging.
            default_cooldown_seconds: Default cooldown period for Throttled state.
            encryption_service: Optional EncryptionService instance. If None, creates one
                using environment variable or settings.
        """
        self._state_store = state_store
        self._observability = observability_manager
        self._default_cooldown_seconds = default_cooldown_seconds

        # Initialize EncryptionService
        if encryption_service is None:
            try:
                self._encryption_service = EncryptionService()
            except EncryptionError as e:
                raise KeyRegistrationError(
                    f"Failed to initialize encryption service: {e}"
                ) from e
        else:
            self._encryption_service = encryption_service

    async def register_key(
        self,
        key_material: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> APIKey:
        """Register a new API key with the system.

        Generates a stable key_id, encrypts the key material, and saves it
        to the StateStore. The key is initialized in Available state.

        Args:
            key_material: Plain text API key to register.
            provider_id: Provider identifier this key belongs to.
            metadata: Optional provider-specific metadata.

        Returns:
            The registered APIKey instance.

        Raises:
            KeyRegistrationError: If registration fails (encryption error,
                StateStore error, invalid provider_id).
        """
        # Validate inputs using validation utilities
        try:
            validate_key_material(key_material)
            validate_provider_id(provider_id)
            if metadata:
                validate_metadata(metadata)
        except ValidationError as e:
            raise KeyRegistrationError(f"Validation failed: {e}") from e

        # Generate stable key_id using UUID
        key_id = str(uuid.uuid4())

        try:
            # Encrypt key material before storage using EncryptionService
            # Fernet.encrypt() returns base64-encoded bytes, so we just decode to string
            encrypted_bytes = self._encryption_service.encrypt(key_material.strip())
            encrypted_key_material = encrypted_bytes.decode('utf-8')
        except EncryptionError as e:
            raise KeyRegistrationError(
                f"Failed to encrypt key material: {e}"
            ) from e

        # Create APIKey instance with Available state
        api_key = APIKey(
            id=key_id,
            key_material=encrypted_key_material,
            provider_id=provider_id.strip().lower(),
            state=KeyState.Available,
            metadata=metadata or {},
        )

        try:
            # Save to StateStore
            await self._state_store.save_key(api_key)
        except StateStoreError as e:
            raise KeyRegistrationError(
                f"Failed to save key to StateStore: {e}"
            ) from e

        # Emit key_registered event
        try:
            await self._observability.emit_event(
                event_type="key_registered",
                payload={
                    "key_id": key_id,
                    "provider_id": api_key.provider_id,
                    "state": api_key.state.value,
                },
                metadata={
                    "created_at": api_key.created_at.isoformat(),
                },
            )
        except Exception as e:
            # Log error but don't fail registration if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit key_registered event: {e}",
                context={"key_id": key_id},
            )

        return api_key

    def _is_valid_transition(self, from_state: KeyState, to_state: KeyState) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current state.
            to_state: Desired new state.

        Returns:
            True if transition is valid, False otherwise.
        """
        if from_state == to_state:
            return True  # No-op transition is always valid

        allowed_transitions = self._VALID_TRANSITIONS.get(from_state, set())
        return to_state in allowed_transitions

    async def update_key_state(
        self,
        key_id: str,
        new_state: KeyState,
        reason: str,
        cooldown_seconds: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> StateTransition:
        """Update the state of an API key with validation and audit trail.

        Validates the state transition, updates the key, creates an audit trail,
        and emits events. Handles cooldown tracking for Throttled state.

        Args:
            key_id: The unique identifier of the key.
            new_state: The desired new state.
            reason: Reason for the state transition (e.g., "rate_limit", "quota_exhausted").
            cooldown_seconds: Optional cooldown period for Throttled state.
                If None and transitioning to Throttled, uses default.
            context: Optional additional context about the transition.

        Returns:
            The StateTransition object representing this transition.

        Raises:
            KeyNotFoundError: If key is not found.
            InvalidStateTransitionError: If transition is not valid.
            StateStoreError: If save operation fails.
        """
        # Retrieve current key from StateStore
        key = await self._state_store.get_key(key_id)
        if key is None:
            raise KeyNotFoundError(f"Key not found: {key_id}")

        from_state = key.state

        # Validate state transition
        if not self._is_valid_transition(from_state, new_state):
            raise InvalidStateTransitionError(
                f"Invalid state transition from {from_state.value} to {new_state.value}"
            )

        # If no state change, return existing transition
        if from_state == new_state:
            # Create a no-op transition for audit trail
            transition = StateTransition(
                entity_type="APIKey",
                entity_id=key_id,
                from_state=from_state.value,
                to_state=new_state.value,
                trigger=reason,
                context=context or {},
            )
            return transition

        # Update key state and timestamp
        now = datetime.utcnow()
        key.state = new_state
        key.state_updated_at = now

        # Handle cooldown tracking for Throttled state
        if new_state == KeyState.Throttled:
            cooldown_duration = cooldown_seconds or self._default_cooldown_seconds
            key.cooldown_until = now + timedelta(seconds=cooldown_duration)
        elif new_state != KeyState.Throttled:
            # Clear cooldown if transitioning away from Throttled
            key.cooldown_until = None

        # Create StateTransition object for audit trail
        transition = StateTransition(
            entity_type="APIKey",
            entity_id=key_id,
            from_state=from_state.value,
            to_state=new_state.value,
            trigger=reason,
            context={
                **(context or {}),
                "cooldown_until": key.cooldown_until.isoformat()
                if key.cooldown_until
                else None,
            },
        )

        try:
            # Save updated key to StateStore
            await self._state_store.save_key(key)

            # Save StateTransition to StateStore
            await self._state_store.save_state_transition(transition)
        except StateStoreError as e:
            raise StateStoreError(f"Failed to save state transition: {e}") from e

        # Emit state_transition event
        try:
            await self._observability.emit_event(
                event_type="state_transition",
                payload={
                    "key_id": key_id,
                    "from_state": from_state.value,
                    "to_state": new_state.value,
                    "reason": reason,
                    "cooldown_until": key.cooldown_until.isoformat()
                    if key.cooldown_until
                    else None,
                },
                metadata={
                    "transition_timestamp": transition.transition_timestamp.isoformat(),
                },
            )
        except Exception as e:
            # Log error but don't fail state transition if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit state_transition event: {e}",
                context={"key_id": key_id, "from_state": from_state.value, "to_state": new_state.value},
            )

        return transition

    async def check_and_recover_states(self) -> list[StateTransition]:
        """Check for keys that need automatic state recovery.

        Automatically transitions:
        - Throttled → Available when cooldown expires
        - Exhausted → Recovering (when quota reset logic triggers, handled separately)

        Returns:
            List of StateTransition objects for recovered keys.
        """
        recovered_transitions: list[StateTransition] = []
        now = datetime.utcnow()

        # Get all keys
        all_keys = await self._state_store.list_keys()

        for key in all_keys:
            # Check if Throttled key's cooldown has expired
            if (
                key.state == KeyState.Throttled
                and key.cooldown_until is not None
                and now >= key.cooldown_until
            ):
                try:
                    transition = await self.update_key_state(
                        key_id=key.id,
                        new_state=KeyState.Available,
                        reason="cooldown_expired",
                        context={"recovered_at": now.isoformat()},
                    )
                    recovered_transitions.append(transition)
                except Exception as e:
                    # Log error but continue checking other keys
                    await self._observability.log(
                        level="ERROR",
                        message=f"Failed to recover key {key.id} from Throttled state: {e}",
                        context={"key_id": key.id},
                    )

        return recovered_transitions

    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve an API key by ID.

        Args:
            key_id: The unique identifier of the key.

        Returns:
            The APIKey if found, None otherwise.
        """
        return await self._state_store.get_key(key_id)

    def _is_key_eligible_by_state(self, key: APIKey, now: datetime) -> bool:
        """Check if a key is eligible based on its state.

        Args:
            key: The APIKey to check.
            now: Current timestamp for cooldown comparison.

        Returns:
            True if key is eligible by state, False otherwise.
        """
        # Disabled keys are never eligible
        if key.state == KeyState.Disabled:
            return False

        # Invalid keys are never eligible
        if key.state == KeyState.Invalid:
            return False

        # Exhausted keys are not eligible (unless Recovering, which is handled below)
        if key.state == KeyState.Exhausted:
            return False

        # Throttled keys are eligible only if cooldown has expired
        if key.state == KeyState.Throttled:
            if key.cooldown_until is None:
                return True  # No cooldown set, consider eligible
            return now >= key.cooldown_until

        # Recovering keys are eligible
        if key.state == KeyState.Recovering:
            return True

        # Available keys are always eligible
        # Unknown state - default to not eligible
        return key.state == KeyState.Available

    async def get_eligible_keys(
        self,
        provider_id: str,
        policy: Callable[[list[APIKey]], list[APIKey]] | None = None,
    ) -> list[APIKey]:
        """Get eligible keys for a provider based on state and policy.

        Filters keys by:
        - State (excludes Disabled, Invalid, Throttled if in cooldown, Exhausted)
        - Policy constraints (if policy provided)

        Args:
            provider_id: Provider identifier to filter keys by.
            policy: Optional policy function that filters keys further.
                Takes a list of APIKey and returns filtered list.

        Returns:
            List of eligible APIKey objects.

        Raises:
            StateStoreError: If querying StateStore fails.
        """
        # Query StateStore for keys by provider_id
        all_keys = await self._state_store.list_keys(provider_id=provider_id)

        # Filter by state
        now = datetime.utcnow()
        state_eligible_keys = [
            key for key in all_keys if self._is_key_eligible_by_state(key, now)
        ]

        # Apply policy-based filtering if policy provided
        if policy is not None:
            try:
                # Policy is a callable that takes list of keys and returns filtered list
                eligible_keys = policy(state_eligible_keys)
                # Ensure result is a list
                if not isinstance(eligible_keys, list):
                    await self._observability.log(
                        level="WARNING",
                        message="Policy function returned non-list result, using state-filtered keys",
                        context={"provider_id": provider_id},
                    )
                    return state_eligible_keys
                return eligible_keys
            except Exception as e:
                # Handle policy evaluation errors gracefully
                await self._observability.log(
                    level="WARNING",
                    message=f"Policy evaluation failed, using state-filtered keys: {e}",
                    context={"provider_id": provider_id},
                )
                return state_eligible_keys

        return state_eligible_keys

    async def revoke_key(self, key_id: str) -> None:
        """Revoke an API key by setting its state to Disabled.

        Revoked keys are immediately excluded from routing via eligibility
        filtering. The system continues operating with remaining keys.

        Args:
            key_id: The unique identifier of the key to revoke.

        Raises:
            KeyNotFoundError: If key is not found.
            StateStoreError: If save operation fails.
        """
        # Retrieve key from StateStore
        key = await self._state_store.get_key(key_id)
        if key is None:
            raise KeyNotFoundError(f"Key not found: {key_id}")

        # Capture previous state before updating
        previous_state = key.state.value
        provider_id = key.provider_id

        # Update key state to Disabled using update_key_state
        # This creates StateTransition and emits events automatically
        await self.update_key_state(
            key_id=key_id,
            new_state=KeyState.Disabled,
            reason="manual_revocation",
            context={"revoked_at": datetime.utcnow().isoformat()},
        )

        # Emit key_revoked event
        try:
            await self._observability.emit_event(
                event_type="key_revoked",
                payload={
                    "key_id": key_id,
                    "provider_id": provider_id,
                    "previous_state": previous_state,
                },
                metadata={
                    "revoked_at": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            # Log error but don't fail revocation if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit key_revoked event: {e}",
                context={"key_id": key_id},
            )

    async def rotate_key(
        self, old_key_id: str, new_key_material: str
    ) -> APIKey:
        """Rotate an API key by updating its key material while preserving key_id.

        Rotation preserves the key_id (stable identity) and updates only the
        key_material. All other attributes (state, metadata, usage counts, etc.)
        are preserved.

        Args:
            old_key_id: The unique identifier of the key to rotate.
            new_key_material: Plain text new API key material.

        Returns:
            The updated APIKey instance with new key material.

        Raises:
            KeyNotFoundError: If key is not found.
            KeyRegistrationError: If encryption fails.
            StateStoreError: If save operation fails.
        """
        if not new_key_material or not new_key_material.strip():
            raise KeyRegistrationError("New key material cannot be empty")

        # Retrieve old key from StateStore
        old_key = await self._state_store.get_key(old_key_id)
        if old_key is None:
            raise KeyNotFoundError(f"Key not found: {old_key_id}")

        # Encrypt new key_material using EncryptionService
        try:
            # Fernet.encrypt() returns base64-encoded bytes, so we just decode to string
            encrypted_bytes = self._encryption_service.encrypt(new_key_material.strip())
            encrypted_new_material = encrypted_bytes.decode('utf-8')
        except EncryptionError as e:
            raise KeyRegistrationError(
                f"Failed to encrypt new key material: {e}"
            ) from e

        # Preserve key_id and all other attributes, update only key_material
        # Create new APIKey instance with updated material
        rotated_key = APIKey(
            id=old_key.id,  # Preserve key_id
            key_material=encrypted_new_material,  # Update material
            provider_id=old_key.provider_id,  # Preserve provider_id
            state=old_key.state,  # Preserve state
            state_updated_at=old_key.state_updated_at,  # Preserve state timestamp
            created_at=old_key.created_at,  # Preserve created_at
            last_used_at=old_key.last_used_at,  # Preserve last_used_at
            usage_count=old_key.usage_count,  # Preserve usage_count
            failure_count=old_key.failure_count,  # Preserve failure_count
            cooldown_until=old_key.cooldown_until,  # Preserve cooldown
            metadata=old_key.metadata,  # Preserve metadata
        )

        try:
            # Save updated key to StateStore
            await self._state_store.save_key(rotated_key)
        except StateStoreError as e:
            raise StateStoreError(f"Failed to save rotated key: {e}") from e

        # Create StateTransition for rotation audit trail
        rotation_transition = StateTransition(
            entity_type="APIKey",
            entity_id=old_key_id,
            from_state=old_key.state.value,
            to_state=rotated_key.state.value,  # State unchanged, but recorded
            trigger="key_rotation",
            context={
                "rotation_timestamp": datetime.utcnow().isoformat(),
                "material_updated": True,
            },
        )

        try:
            # Save StateTransition to StateStore
            await self._state_store.save_state_transition(rotation_transition)
        except StateStoreError as e:
            # Log error but don't fail rotation if transition save fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to save rotation transition: {e}",
                context={"key_id": old_key_id},
            )

        # Emit key_rotated event
        try:
            await self._observability.emit_event(
                event_type="key_rotated",
                payload={
                    "key_id": old_key_id,
                    "provider_id": rotated_key.provider_id,
                    "state": rotated_key.state.value,
                },
                metadata={
                    "rotated_at": datetime.utcnow().isoformat(),
                    "preserved_key_id": True,
                },
            )
        except Exception as e:
            # Log error but don't fail rotation if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit key_rotated event: {e}",
                context={"key_id": old_key_id},
            )

        return rotated_key

    async def get_key_material(self, key_id: str) -> str:
        """Get decrypted key material for an API key.

        Decrypts the key material on demand. The decrypted key is returned
        but not stored in memory longer than necessary. Logs an audit event
        for key access.

        Args:
            key_id: The unique identifier of the key.

        Returns:
            Decrypted plain text API key material.

        Raises:
            KeyNotFoundError: If key is not found.
            EncryptionError: If decryption fails.
        """
        # Retrieve key from StateStore
        key = await self._state_store.get_key(key_id)
        if key is None:
            raise KeyNotFoundError(f"Key not found: {key_id}")

        try:
            # Decrypt key material on demand
            # Fernet tokens are already base64-encoded, so we just encode the string to bytes
            from datetime import datetime

            encrypted_bytes = key.key_material.encode('utf-8')
            decrypted_material = self._encryption_service.decrypt(encrypted_bytes)
            
            # Log audit event for key access (decryption)
            try:
                await self._observability.emit_event(
                    event_type="key_access",
                    payload={
                        "key_id": key_id,
                        "provider_id": key.provider_id,
                        "operation": "decrypt",
                        "result": "success",
                    },
                    metadata={
                        "timestamp": datetime.utcnow().isoformat(),
                        "access_type": "key_material_decryption",
                    },
                )
            except Exception as e:
                # Log error but don't fail key access if audit logging fails
                await self._observability.log(
                    level="WARNING",
                    message=f"Failed to emit key_access audit event: {e}",
                    context={"key_id": key_id},
                )
            
            return decrypted_material
        except EncryptionError as e:
            # Log failed access attempt
            try:
                await self._observability.emit_event(
                    event_type="key_access",
                    payload={
                        "key_id": key_id,
                        "provider_id": key.provider_id,
                        "operation": "decrypt",
                        "result": "failure",
                        "error": str(e),
                    },
                    metadata={
                        "timestamp": datetime.utcnow().isoformat(),
                        "access_type": "key_material_decryption",
                    },
                )
            except Exception:
                # Ignore audit logging errors for failed access
                pass
            
            raise EncryptionError(
                f"Failed to decrypt key material for key {key_id}: {e}"
            ) from e

