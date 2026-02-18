"""Orchestrator — coordinates RetrievalAgent -> ReasoningAgent flow.

Accepts an async callback for streaming SSE events so the endpoint can
push intermediate steps (agent_step, sql, token, done) to the client.

Includes a fast-path detector that skips the RetrievalAgent when the
question is simple enough (MTO lookup, basic SQL).
"""

import json
import logging
import re
from typing import Any, Callable, Coroutine, Dict, Optional

from src.agents.base import AgentLLMClient, AgentStep, ToolDefinition
from src.agents.chat.retrieval_agent import RetrievalAgent
from src.agents.chat.reasoning_agent import ReasoningAgent

logger = logging.getLogger(__name__)

# Pattern for MTO numbers (e.g., AK2510034, DS261017S, AS2601037)
_MTO_PATTERN = re.compile(r"[A-Z]{2}\d{5,}")


def _detect_fast_path(question: str) -> Optional[str]:
    """Detect if we can skip the RetrievalAgent and go straight to reasoning.

    Returns a synthetic data plan if fast-path is possible, None otherwise.
    """
    q = question.strip()

    # Fast path 1: MTO-specific question (contains an MTO number)
    mto_match = _MTO_PATTERN.search(q)
    if mto_match:
        mto_no = mto_match.group()
        return (
            f"用户询问特定MTO编号 {mto_no} 的信息。\n"
            f"直接使用 mto_lookup 工具查询 {mto_no} 的完整状态即可。"
        )

    # Fast path 2: Schema/field question
    schema_keywords = ["哪些字段", "表结构", "有哪些列", "字段含义", "表有什么"]
    if any(kw in q for kw in schema_keywords):
        # Extract table name if mentioned
        table_names = [
            "cached_production_orders", "cached_production_bom",
            "cached_production_receipts", "cached_purchase_receipts",
            "cached_purchase_orders", "cached_picking_records",
            "cached_delivery_records",
        ]
        for tn in table_names:
            if tn in q:
                return f"用户询问 {tn} 表的结构。使用 schema_lookup 工具查询表结构并回答。"
        return "用户询问数据库表结构。所有表结构已在系统提示中提供，直接回答即可。"

    return None

# Type alias for the async event callback
OnEvent = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]


class AgentChatOrchestrator:
    """Coordinates the dual-agent pipeline for a single chat turn.

    Flow:
        1. RetrievalAgent explores schema/config -> produces data plan
        2. ReasoningAgent uses plan to generate SQL, execute, and answer
        3. Events are emitted via on_event callback throughout

    Event types emitted:
        - {"type": "agent_step", "agent": str, "step_number": int,
           "tool_name": str, "tool_args": dict}
        - {"type": "data_plan", "content": str}
        - {"type": "sql", "query": str}
        - {"type": "token", "content": str}
        - {"type": "error", "message": str}
        - {"type": "done"}
    """

    def __init__(
        self,
        llm_client: AgentLLMClient,
        schema_tool: ToolDefinition,
        config_tool: ToolDefinition,
        sql_tool: ToolDefinition,
        mto_tool: ToolDefinition,
    ) -> None:
        self._llm_client = llm_client
        self._schema_tool = schema_tool
        self._config_tool = config_tool
        self._sql_tool = sql_tool
        self._mto_tool = mto_tool

    async def run(
        self,
        question: str,
        mto_context: Optional[str] = None,
        on_event: Optional[OnEvent] = None,
    ) -> None:
        """Execute the full retrieval -> reasoning pipeline.

        Args:
            question: The user's question.
            mto_context: Optional MTO context string (e.g., current MTO number).
            on_event: Async callback receiving event dicts for SSE streaming.
        """
        async def emit(event: Dict[str, Any]) -> None:
            if on_event:
                try:
                    await on_event(event)
                except Exception as exc:
                    logger.warning("on_event callback failed: %s", exc)

        try:
            # Check fast path — skip retrieval for simple questions
            fast_plan = _detect_fast_path(question)

            if fast_plan:
                logger.info("Fast path detected, skipping retrieval agent")
                await emit({
                    "type": "agent_step",
                    "agent": "retrieval",
                    "step_number": 0,
                    "tool_name": "fast_path",
                    "tool_args": {},
                })
                data_plan = fast_plan
                await emit({"type": "data_plan", "content": data_plan})
            else:
                # Phase 1: Full Retrieval
                await emit({
                    "type": "agent_step",
                    "agent": "retrieval",
                    "step_number": 0,
                    "tool_name": "start",
                    "tool_args": {},
                })

                retrieval = RetrievalAgent(
                    schema_tool=self._schema_tool,
                    config_tool=self._config_tool,
                    llm_client=self._llm_client,
                )
                retrieval_result = await retrieval.run(question, mto_context)

                if retrieval_result.error:
                    await emit({
                        "type": "error",
                        "message": f"检索规划失败: {retrieval_result.error}",
                    })
                    await emit({"type": "done"})
                    return

                data_plan = retrieval_result.answer
                await emit({"type": "data_plan", "content": data_plan})

                # Emit retrieval steps
                for step in retrieval_result.steps:
                    if step.action == "tool_call":
                        await emit({
                            "type": "agent_step",
                            "agent": "retrieval",
                            "step_number": step.step_number,
                            "tool_name": step.tool_name or "",
                            "tool_args": step.tool_args or {},
                        })

            # Phase 2: Reasoning
            def on_reasoning_step(step: AgentStep) -> None:
                """Synchronous callback — we'll emit events inline instead."""
                pass

            reasoning = ReasoningAgent(
                sql_tool=self._sql_tool,
                mto_tool=self._mto_tool,
                llm_client=self._llm_client,
            )

            # Collect steps for post-hoc emission since runner callback is sync
            reasoning_result = await reasoning.run(
                question=question,
                data_plan=data_plan,
                mto_context=mto_context,
            )

            # Emit reasoning steps
            for step in reasoning_result.steps:
                if step.action == "tool_call":
                    await emit({
                        "type": "agent_step",
                        "agent": "reasoning",
                        "step_number": step.step_number,
                        "tool_name": step.tool_name or "",
                        "tool_args": step.tool_args or {},
                    })
                    # If the tool was sql_query, emit the SQL event
                    if step.tool_name == "sql_query" and step.tool_args:
                        await emit({
                            "type": "sql",
                            "query": step.tool_args.get("query", ""),
                        })

            if reasoning_result.error:
                await emit({
                    "type": "error",
                    "message": f"推理分析失败: {reasoning_result.error}",
                })
            elif reasoning_result.answer:
                await emit({
                    "type": "token",
                    "content": reasoning_result.answer,
                })

        except Exception as exc:
            logger.exception("Orchestrator error: %s", exc)
            await emit({
                "type": "error",
                "message": f"处理失败: {exc}",
            })
        finally:
            await emit({"type": "done"})
