"""
API endpoints for dashboard key management.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path
from pydantic import BaseModel, Field

from apikeyrouter.domain.components.key_manager import KeyManager, KeyState
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.state_store import StateQuery, StateStore
from apikeyrouter_proxy.dependencies import (
    get_key_manager,
    get_observability_manager,
    get_state_store,
)

router = APIRouter()


def get_key_manager_dependency(
    state_store: Annotated[StateStore, Depends(get_state_store)],
    observability_manager: Annotated[ObservabilityManager, Depends(get_observability_manager)],
) -> KeyManager:
    return get_key_manager(state_store, observability_manager)


class KeyCreateRequest(BaseModel):
    key_material: str = Field(..., description="The API key material.")
    provider_id: str = Field(..., description="The ID of the provider for this key.")
    metadata: dict[str, Any] | None = Field(None, description="Optional metadata for the key.")

class KeyStateUpdateRequest(BaseModel):
    state: KeyState = Field(..., description="The new state for the key.")
    reason: str = Field(..., description="The reason for the state change.")

@router.get("/keys")
async def list_keys(
    state_store: Annotated[StateStore, Depends(get_state_store)],
) -> dict[str, Any]:
    """
    List all API keys with their current states.
    """
    keys = await state_store.list_keys()
    return {"keys": [key.model_dump() for key in keys]}


@router.post("/keys")
async def create_key(
    request: Annotated[KeyCreateRequest, Body(...)],
    key_manager: Annotated[KeyManager, Depends(get_key_manager_dependency)],
) -> dict[str, Any]:
    """
    Add a new API key.
    """
    new_key = await key_manager.register_key(
        key_material=request.key_material,
        provider_id=request.provider_id,
        metadata=request.metadata,
    )
    return {"key": new_key.model_dump()}


@router.put("/keys/{key_id}/state")
async def update_key_state(
    key_id: Annotated[str, Path(..., description="The ID of the key to update.")],
    request: Annotated[KeyStateUpdateRequest, Body(...)],
    key_manager: Annotated[KeyManager, Depends(get_key_manager_dependency)],
) -> dict[str, Any]:
    """
    Update the state of an API key.
    """
    transition = await key_manager.update_key_state(
        key_id=key_id,
        new_state=request.state,
        reason=request.reason,
    )
    return {"transition": transition.model_dump()}


@router.get("/keys/{key_id}/audit")
async def get_key_audit_trail(
    key_id: Annotated[str, Path(..., description="The ID of the key to audit.")],
    state_store: Annotated[StateStore, Depends(get_state_store)],
) -> dict[str, Any]:
    """
    Get the audit trail for an API key.
    """
    query = StateQuery(entity_type="StateTransition", key_id=key_id)
    transitions = await state_store.query_state(query)
    return {"audit_trail": [t.model_dump() for t in transitions]}
