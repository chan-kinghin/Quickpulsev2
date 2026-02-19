"""Core agent abstractions — models, configs, and LLM client with tool support.

Follows the same composition pattern as DeepSeekClient but adds function-calling
(tool_call) support for the agent loop.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError
from openai.types.chat import ChatCompletionMessageToolCall

from src.config import DeepSeekConfig
from src.exceptions import ChatConnectionError, ChatRateLimitError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    """Describes a tool the agent can call.

    Attributes:
        name: Unique tool identifier (e.g., "sql_query").
        description: Chinese/English description for the LLM.
        parameters: JSON Schema dict describing the tool's parameters.
        handler: Async callable(kwargs) -> str that executes the tool.
    """

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Coroutine[Any, Any, str]]

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert to OpenAI function-calling tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCallResult:
    """Result of executing a single tool call."""

    tool_name: str
    tool_call_id: str
    arguments: Dict[str, Any]
    result: str
    error: Optional[str] = None


@dataclass
class AgentStep:
    """One step in the agent's reasoning trace."""

    step_number: int
    action: str  # "tool_call" | "final_answer"
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[str] = None
    content: Optional[str] = None
    tokens_used: int = 0


@dataclass
class AgentResult:
    """Final result of an agent run."""

    answer: str
    steps: List[AgentStep] = field(default_factory=list)
    total_tokens: int = 0
    error: Optional[str] = None


@dataclass
class AgentConfig:
    """Configuration for an agent run.

    Attributes:
        max_steps: Maximum tool-call iterations before stopping.
        max_tokens_budget: Token budget for the entire run (32K default).
        temperature: LLM sampling temperature.
        system_prompt: The agent's system prompt.
    """

    max_steps: int = 5
    max_tokens_budget: int = 48000
    temperature: float = 0.1
    system_prompt: str = ""


# ---------------------------------------------------------------------------
# LLM client with tool-call support
# ---------------------------------------------------------------------------


class AgentLLMClient:
    """Async LLM client with function-calling support.

    Composes AsyncOpenAI (same config as DeepSeekClient) but adds the
    ``tools`` parameter for structured tool use.
    """

    def __init__(self, config: DeepSeekConfig) -> None:
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=float(config.timeout_seconds),
        )
        self._model = config.model
        self._max_tokens = config.max_tokens
        self._default_temperature = config.temperature

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request with tools.

        Returns a dict with:
            - ``role``: "assistant"
            - ``content``: text content (may be None)
            - ``tool_calls``: list of tool call dicts (may be empty)
            - ``usage``: token usage dict
        """
        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "max_tokens": self._max_tokens,
                "temperature": temperature or self._default_temperature,
                "stream": False,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await self._client.chat.completions.create(**kwargs)

            msg = response.choices[0].message
            usage = response.usage

            tool_calls_data: List[Dict[str, Any]] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

            return {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": tool_calls_data,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
            }
        except RateLimitError as exc:
            logger.warning("Agent LLM rate limit: %s", exc)
            raise ChatRateLimitError(str(exc)) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            logger.error("Agent LLM connection error: %s", exc)
            raise ChatConnectionError(str(exc)) from exc

    async def close(self) -> None:
        """Shutdown the underlying httpx client."""
        await self._client.close()


# ---------------------------------------------------------------------------
# Tool-call parsing fallback (for models that embed JSON in content)
# ---------------------------------------------------------------------------

# Regex to locate the start of tool-call JSON objects in content.
# We only use this to find candidates; actual extraction uses balanced-brace
# parsing to handle nested JSON (e.g., arguments containing dicts).
_TOOL_CALL_START = re.compile(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*\{')


def _extract_json_object(text: str, start: int) -> Optional[str]:
    """Extract a JSON object with balanced braces starting at *start*.

    Returns the substring ``text[start:end]`` (inclusive of the outer
    braces) or ``None`` if braces are unbalanced.
    """
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_tool_calls_from_content(content: str) -> List[Dict[str, Any]]:
    """Attempt to extract tool call JSON from plain text content.

    This is a fallback for LLMs that embed function calls in their
    text response instead of using the structured tool_calls field.
    Uses balanced-brace matching so nested JSON arguments are handled.

    Returns:
        List of dicts with ``name`` and ``arguments`` keys.
    """
    results: List[Dict[str, Any]] = []
    for match in _TOOL_CALL_START.finditer(content):
        obj_str = _extract_json_object(content, match.start())
        if obj_str is None:
            continue
        try:
            obj = json.loads(obj_str)
            name = obj.get("name")
            arguments = obj.get("arguments")
            if name and isinstance(arguments, dict):
                results.append({
                    "id": f"fallback_{name}_{len(results)}",
                    "name": name,
                    "arguments": json.dumps(arguments),
                })
        except json.JSONDecodeError:
            logger.debug("Failed to parse fallback tool call: %s", obj_str[:200])
    return results


# ---------------------------------------------------------------------------
# Abstract base for specialized agents
# ---------------------------------------------------------------------------


class AgentBase(ABC):
    """Abstract base class for specialized agents (retrieval, reasoning, etc.)."""

    def __init__(self, name: str, config: AgentConfig) -> None:
        self.name = name
        self.config = config

    @abstractmethod
    def get_tools(self) -> List[ToolDefinition]:
        """Return the tools this agent can use."""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        ...
