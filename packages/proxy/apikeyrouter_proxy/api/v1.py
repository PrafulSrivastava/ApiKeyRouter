"""API v1 routes for the APIKeyRouter Proxy."""

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions() -> dict[str, Any]:
    return {"message": "This is a simulated response from the APIKeyRouter Proxy."}
