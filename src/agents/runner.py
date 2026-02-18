"""Agent runner — core async agent loop (LLM -> tool_call -> execute -> loop).

Implements the iterative reasoning loop inspired by Agent-OM's multi-step
approach. The runner calls the LLM, checks for tool calls, executes them,
feeds results back, and repeats until the LLM produces a final answer or
max_steps is reached.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from src.agents.base import (
    AgentConfig,
    AgentLLMClient,
    AgentResult,
    AgentStep,
    ToolCallResult,
    extract_tool_calls_from_content,
)
from src.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRunner:
    """Executes the agent reasoning loop.

    The loop:
    1. Send messages + tools to LLM
    2. If LLM returns tool_calls -> execute each tool -> append results
    3. Repeat until LLM returns content without tool_calls, or max_steps hit
    4. Return AgentResult with answer + step trace

    Attributes:
        client: The LLM client with tool-calling support.
        registry: Tool registry containing available tools.
        config: Agent configuration (max_steps, token budget, etc.).
        on_step: Optional callback invoked after each step (for SSE streaming).
    """

    def __init__(
        self,
        client: AgentLLMClient,
        registry: ToolRegistry,
        config: AgentConfig,
        on_step: Optional[Callable[[AgentStep], None]] = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.config = config
        self.on_step = on_step

    async def run(
        self,
        user_message: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
    ) -> AgentResult:
        """Run the agent loop to completion.

        Args:
            user_message: The user's question or instruction.
            context_messages: Optional prior conversation messages.

        Returns:
            AgentResult with the final answer and step trace.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.config.system_prompt},
        ]
        if context_messages:
            messages.extend(context_messages)
        messages.append({"role": "user", "content": user_message})

        openai_tools = self.registry.to_openai_tools()
        steps: List[AgentStep] = []
        total_tokens = 0

        for step_num in range(1, self.config.max_steps + 1):
            # Check token budget
            if total_tokens >= self.config.max_tokens_budget:
                logger.warning(
                    "Token budget exhausted (%d/%d), stopping",
                    total_tokens,
                    self.config.max_tokens_budget,
                )
                break

            # Call LLM
            try:
                response = await self.client.chat_with_tools(
                    messages=messages,
                    tools=openai_tools,
                    temperature=self.config.temperature,
                )
            except Exception as exc:
                logger.error("Agent LLM call failed at step %d: %s", step_num, exc)
                return AgentResult(
                    answer="",
                    steps=steps,
                    total_tokens=total_tokens,
                    error=str(exc),
                )

            total_tokens += response["usage"].get("total_tokens", 0)
            content = response.get("content") or ""
            tool_calls = response.get("tool_calls", [])

            # Fallback: if no native tool_calls, try extracting from content
            if not tool_calls and content:
                tool_calls = extract_tool_calls_from_content(content)
                if tool_calls:
                    logger.info(
                        "Extracted %d tool call(s) from content (fallback)",
                        len(tool_calls),
                    )

            if not tool_calls:
                # Final answer — no more tool calls
                step = AgentStep(
                    step_number=step_num,
                    action="final_answer",
                    content=content,
                    tokens_used=response["usage"].get("total_tokens", 0),
                )
                steps.append(step)
                self._notify_step(step)
                return AgentResult(
                    answer=content,
                    steps=steps,
                    total_tokens=total_tokens,
                )

            # Execute tool calls
            # Build assistant message with tool_calls for conversation history
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            else:
                assistant_msg["content"] = None

            # Format tool_calls for the message history
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"] if isinstance(tc["arguments"], str) else json.dumps(tc["arguments"]),
                    },
                }
                for tc in tool_calls
            ]
            messages.append(assistant_msg)

            for tc in tool_calls:
                tc_result = await self._execute_tool_call(tc)

                step = AgentStep(
                    step_number=step_num,
                    action="tool_call",
                    tool_name=tc_result.tool_name,
                    tool_args=tc_result.arguments,
                    tool_result=tc_result.result,
                    tokens_used=0,
                )
                steps.append(step)
                self._notify_step(step)

                # Append tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_result.tool_call_id,
                    "content": tc_result.result,
                })

        # Max steps reached without final answer
        logger.warning("Agent hit max_steps (%d) without final answer", self.config.max_steps)
        return AgentResult(
            answer=content if content else "达到最大推理步数限制，请尝试简化问题。",
            steps=steps,
            total_tokens=total_tokens,
            error="max_steps_reached",
        )

    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> ToolCallResult:
        """Execute a single tool call and return the result."""
        name = tool_call["name"]
        call_id = tool_call.get("id", f"call_{name}")
        raw_args = tool_call.get("arguments", "{}")

        # Parse arguments
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                return ToolCallResult(
                    tool_name=name,
                    tool_call_id=call_id,
                    arguments={},
                    result="",
                    error=f"Invalid JSON arguments: {raw_args}",
                )
        else:
            args = raw_args

        # Find and execute tool
        tool = self.registry.get(name)
        if not tool:
            error_msg = f"未知工具: {name}"
            logger.warning(error_msg)
            return ToolCallResult(
                tool_name=name,
                tool_call_id=call_id,
                arguments=args,
                result=error_msg,
                error=error_msg,
            )

        try:
            result = await tool.handler(**args)
            return ToolCallResult(
                tool_name=name,
                tool_call_id=call_id,
                arguments=args,
                result=result,
            )
        except Exception as exc:
            error_msg = f"工具执行失败 ({name}): {exc}"
            logger.error(error_msg)
            return ToolCallResult(
                tool_name=name,
                tool_call_id=call_id,
                arguments=args,
                result=error_msg,
                error=error_msg,
            )

    def _notify_step(self, step: AgentStep) -> None:
        """Invoke the on_step callback if set."""
        if self.on_step:
            try:
                self.on_step(step)
            except Exception as exc:
                logger.warning("on_step callback failed: %s", exc)
