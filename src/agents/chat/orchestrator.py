"""Orchestrator — coordinates RetrievalAgent -> ReasoningAgent flow.

Accepts an async callback for streaming SSE events so the endpoint can
push intermediate steps (agent_step, sql, token, done) to the client.
"""

import json
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from src.agents.base import AgentLLMClient, AgentStep, ToolDefinition
from src.agents.chat.retrieval_agent import RetrievalAgent
from src.agents.chat.reasoning_agent import ReasoningAgent

logger = logging.getLogger(__name__)

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
            # Phase 1: Retrieval
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
