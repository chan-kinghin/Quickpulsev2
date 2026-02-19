"""Agent-enhanced chat endpoints — SSE streaming with dual-agent architecture.

Parallel endpoint to /api/chat/stream. Uses RetrievalAgent + ReasoningAgent
for more capable data exploration and self-correcting SQL execution.

IMPORTANT: Do NOT use ``from __future__ import annotations`` here — it breaks
Pydantic model resolution with FastAPI's dependency injection.
"""

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-chat", tags=["agent-chat"])


# ---------------------------------------------------------------------------
# Request / response models (same shape as existing chat)
# ---------------------------------------------------------------------------

class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    messages: List[AgentChatMessage]
    mto_context: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_mto_context_str(mto_context: Optional[dict]) -> Optional[str]:
    """Extract an MTO context string from the request's mto_context dict."""
    if not mto_context:
        return None
    parent = mto_context.get("parent_item") or {}
    mto_number = parent.get("mto_number")
    if mto_number:
        return f"用户正在查看 MTO: {mto_number}"
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def agent_chat_status(request: Request, current_user: str = Depends(get_current_user)):
    """Check if the agent chat feature is available."""
    from src.config import AgentLLMConfig
    agent_config = AgentLLMConfig()
    if not agent_config.is_available():
        return {"available": False, "model": None, "mode": "agent"}
    resolved = agent_config.resolve()
    return {"available": True, "model": resolved.model, "mode": "agent"}


@router.post("/stream")
@limiter.limit("20/minute")
async def agent_chat_stream(
    request: Request,
    body: AgentChatRequest,
    current_user: str = Depends(get_current_user),
):
    """SSE streaming agent chat endpoint — dual-agent mode."""
    from src.config import AgentLLMConfig
    agent_config = AgentLLMConfig()
    resolved = agent_config.resolve()
    if not resolved or not resolved.api_key:
        raise HTTPException(status_code=503, detail="Agent chat not available")

    return StreamingResponse(
        _agent_stream(request, body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _agent_stream(request: Request, body: AgentChatRequest):
    """Run the dual-agent pipeline and yield SSE events."""
    # Lazy imports to avoid circular dependencies and keep router file light
    from src.agents.base import AgentLLMClient
    from src.agents.tools.sql_query import create_sql_query_tool
    from src.agents.tools.schema_lookup import create_schema_lookup_tool
    from src.agents.tools.mto_lookup import create_mto_lookup_tool
    from src.agents.tools.config_lookup import create_config_lookup_tool
    from src.agents.chat.orchestrator import AgentChatOrchestrator

    # Get dependencies from app state
    db = request.app.state.db
    mto_handler = request.app.state.mto_handler
    mto_config = getattr(request.app.state, "mto_config", None)

    if mto_config is None:
        yield _sse_event({"type": "error", "message": "MTO config not available"})
        yield _sse_event({"type": "done"})
        return

    # Create LLM client — use AgentLLMConfig (AGENT_*) with fallback to DEEPSEEK_*
    from src.config import AgentLLMConfig
    agent_config = AgentLLMConfig().resolve()
    llm_client = AgentLLMClient(agent_config)
    try:
        schema_tool = create_schema_lookup_tool(db)
        config_tool = create_config_lookup_tool(mto_config)
        sql_tool = create_sql_query_tool(db)
        mto_tool = create_mto_lookup_tool(mto_handler)

        orchestrator = AgentChatOrchestrator(
            llm_client=llm_client,
            schema_tool=schema_tool,
            config_tool=config_tool,
            sql_tool=sql_tool,
            mto_tool=mto_tool,
        )

        # Use an asyncio.Queue to bridge the orchestrator's async callback
        # with the SSE generator
        event_queue = asyncio.Queue()

        async def on_event(event):
            await event_queue.put(event)

        # Extract user question (last user message)
        user_question = ""
        for msg in reversed(body.messages):
            if msg.role == "user":
                user_question = msg.content
                break

        if not user_question:
            yield _sse_event({"type": "error", "message": "No user message found"})
            yield _sse_event({"type": "done"})
            return

        mto_context_str = _build_mto_context_str(body.mto_context)

        # Run orchestrator in background, yield events as they arrive
        async def run_orchestrator():
            try:
                await asyncio.wait_for(
                    orchestrator.run(
                        question=user_question,
                        mto_context=mto_context_str,
                        on_event=on_event,
                    ),
                    timeout=300,  # 5 min max
                )
            except asyncio.TimeoutError:
                await event_queue.put({"type": "error", "content": "Request timed out after 5 minutes"})
                await event_queue.put({"type": "done"})
            except Exception as exc:
                logger.exception("Orchestrator failed: %s", exc)
                await event_queue.put({"type": "error", "message": str(exc)})
                await event_queue.put({"type": "done"})

        task = asyncio.create_task(run_orchestrator())

        # Yield events from the queue until we see "done"
        while True:
            event = await event_queue.get()
            yield _sse_event(event)
            if event.get("type") == "done":
                break

        # Ensure the task is complete
        await task

    except Exception as exc:
        logger.exception("Agent stream error: %s", exc)
        yield _sse_event({"type": "error", "message": str(exc)})
        yield _sse_event({"type": "done"})
    finally:
        await llm_client.close()
