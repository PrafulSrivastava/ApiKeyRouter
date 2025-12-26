"""API v1 routes for the APIKeyRouter Proxy."""

from fastapi import APIRouter

router = APIRouter()

@router.post("/chat/completions")
async def chat_completions():
    return {"message": "This is a simulated response from the APIKeyRouter Proxy."}
