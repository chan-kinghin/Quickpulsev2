"""Chat endpoints — SSE streaming for multi-provider LLM integration."""

import json
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.chat.context import build_sql_result_context
from src.chat.prompts import SYSTEM_PROMPT_ANALYTICS, SYSTEM_PROMPT_SUMMARY
from src.chat.sql_guard import validate_sql
from src.exceptions import ChatError, ChatSQLError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    mto_context: Optional[dict] = None


class ProviderSwitchRequest(BaseModel):
    provider: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_sql(text: str) -> Optional[str]:
    """Extract a SQL query from a ```sql ... ``` fenced block."""
    m = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _build_system_prompt(body: ChatRequest) -> str:
    """Build the analytics system prompt, optionally injecting MTO context."""
    prompt = SYSTEM_PROMPT_ANALYTICS
    if body.mto_context:
        parent = body.mto_context.get("parent_item") or {}
        mto_number = parent.get("mto_number")
        if mto_number:
            prompt += (
                f"\n\n## 当前上下文\n"
                f"用户正在查看 MTO: {mto_number}，"
                f"如果问题与当前MTO相关，请在SQL中使用 "
                f"WHERE mto_number = '{mto_number}'"
            )
    return prompt


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_PROVIDER_CONFIGS = {"deepseek": "deepseek", "qwen": "qwen"}
_PROVIDER_LABELS = {"deepseek": "DeepSeek", "qwen": "Qwen"}


@router.get("/status")
async def chat_status(request: Request):
    """Check if the chat feature is available and list providers."""
    providers = getattr(request.app.state, "chat_providers", {})
    active = getattr(request.app.state, "active_chat_provider", None)
    if not providers:
        return {"available": False, "model": None, "providers": [], "active": None}

    config = request.app.state.config
    provider_list = []
    for name in providers:
        cfg = getattr(config, _PROVIDER_CONFIGS.get(name, name), None)
        provider_list.append({
            "name": name,
            "label": _PROVIDER_LABELS.get(name, name),
            "model": cfg.model if cfg else "",
        })

    active_cfg = getattr(config, _PROVIDER_CONFIGS.get(active, active), None)
    return {
        "available": True,
        "model": active_cfg.model if active_cfg else "",
        "providers": provider_list,
        "active": active,
    }


@router.post("/provider")
async def switch_provider(
    request: Request,
    body: ProviderSwitchRequest,
    current_user: str = Depends(get_current_user),
):
    """Switch the active LLM provider."""
    providers = getattr(request.app.state, "chat_providers", {})
    if body.provider not in providers:
        available = list(providers.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{body.provider}'. Available: {available}",
        )
    request.app.state.active_chat_provider = body.provider
    request.app.state.chat_client = providers[body.provider]
    config = request.app.state.config
    cfg = getattr(config, _PROVIDER_CONFIGS.get(body.provider, body.provider), None)
    return {
        "active": body.provider,
        "model": cfg.model if cfg else "",
    }


@router.post("/stream")
@limiter.limit("20/minute")
async def stream_chat(
    request: Request,
    body: ChatRequest,
    current_user: str = Depends(get_current_user),
):
    """SSE streaming chat endpoint — analytics mode (SQL generation + summarization)."""
    client = request.app.state.chat_client
    if client is None:
        raise HTTPException(status_code=503, detail="Chat service not configured")

    return StreamingResponse(
        _analytics_stream(client, body, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _analytics_stream(client, body: ChatRequest, request: Request):
    """Analytics mode: generate SQL -> validate -> execute -> summarize."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    system_prompt = _build_system_prompt(body)

    # Step 1: Ask LLM for SQL
    try:
        sql_response = await client.chat(messages, system_prompt)
    except ChatError as exc:
        yield _sse_event({"type": "error", "message": str(exc)})
        yield _sse_event({"type": "done"})
        return

    raw_sql = _extract_sql(sql_response)
    if not raw_sql:
        # LLM didn't return SQL — stream its response as-is
        yield _sse_event({"type": "token", "content": sql_response})
        yield _sse_event({"type": "done"})
        return

    # Step 2: Validate SQL
    try:
        safe_sql = validate_sql(raw_sql)
    except ChatSQLError as exc:
        yield _sse_event({"type": "error", "message": f"SQL验证失败: {exc}"})
        yield _sse_event({"type": "done"})
        return

    yield _sse_event({"type": "sql", "query": safe_sql})

    # Step 3: Execute SQL
    db = request.app.state.db
    try:
        rows, column_names = await db.execute_read_with_columns(safe_sql)
    except Exception as exc:
        logger.warning("SQL execution failed: %s", exc)
        yield _sse_event({"type": "error", "message": f"SQL执行失败: {exc}"})
        yield _sse_event({"type": "done"})
        return

    yield _sse_event({
        "type": "sql_result",
        "columns": column_names,
        "rows": [list(r) for r in rows[:50]],
        "total_rows": len(rows),
    })

    # Step 4: Stream a natural-language summary of the results
    result_context = build_sql_result_context(rows, column_names)
    summary_messages = messages + [
        {"role": "assistant", "content": f"```sql\n{safe_sql}\n```"},
        {"role": "user", "content": f"查询结果如下，请用中文简要总结：\n{result_context}"},
    ]

    try:
        async for delta in client.stream_chat(summary_messages, SYSTEM_PROMPT_SUMMARY):
            yield _sse_event({"type": "token", "content": delta})
    except ChatError as exc:
        yield _sse_event({"type": "error", "message": str(exc)})
    finally:
        yield _sse_event({"type": "done"})
