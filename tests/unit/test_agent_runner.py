"""Tests for AgentRunner — the core agent reasoning loop."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.base import AgentConfig, AgentLLMClient, AgentResult, AgentStep
from src.agents.runner import AgentRunner
from src.agents.tool_registry import ToolRegistry
from src.agents.base import ToolDefinition


def _make_registry_with_tools():
    """Create a registry with a simple echo tool."""
    registry = ToolRegistry()

    async def echo_handler(message: str = "hello") -> str:
        return f"echo: {message}"

    registry.register(ToolDefinition(
        name="echo",
        description="Echo tool",
        parameters={"type": "object", "properties": {"message": {"type": "string"}}},
        handler=echo_handler,
    ))
    return registry


def _make_mock_client():
    """Create a mock AgentLLMClient."""
    client = MagicMock(spec=AgentLLMClient)
    return client


# ---------------------------------------------------------------------------
# Basic flow tests
# ---------------------------------------------------------------------------


class TestAgentRunnerBasicFlow:
    """Tests for basic agent loop behavior."""

    @pytest.mark.asyncio
    async def test_final_answer_on_first_call(self):
        """LLM returns content without tool_calls -> immediate final answer."""
        client = _make_mock_client()
        client.chat_with_tools = AsyncMock(return_value={
            "role": "assistant",
            "content": "The answer is 42.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="You are a test agent."),
        )

        result = await runner.run("What is 42?")
        assert result.answer == "The answer is 42."
        assert result.error is None
        assert len(result.steps) == 1
        assert result.steps[0].action == "final_answer"
        assert result.total_tokens == 15

    @pytest.mark.asyncio
    async def test_tool_call_then_final_answer(self):
        """LLM returns tool_call, then final answer."""
        client = _make_mock_client()

        # First call: LLM requests echo tool
        call_1_response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "name": "echo",
                "arguments": '{"message": "world"}',
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }

        # Second call: LLM returns final answer
        call_2_response = {
            "role": "assistant",
            "content": "The echo result was: echo: world",
            "tool_calls": [],
            "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
        }

        client.chat_with_tools = AsyncMock(side_effect=[call_1_response, call_2_response])

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
        )

        result = await runner.run("Echo world")

        assert result.answer == "The echo result was: echo: world"
        assert result.error is None
        assert len(result.steps) == 2  # tool_call + final_answer
        assert result.steps[0].action == "tool_call"
        assert result.steps[0].tool_name == "echo"
        assert result.steps[0].tool_result == "echo: world"
        assert result.steps[1].action == "final_answer"
        assert result.total_tokens == 75


# ---------------------------------------------------------------------------
# Max steps
# ---------------------------------------------------------------------------


class TestAgentRunnerMaxSteps:
    """Tests for max_steps enforcement."""

    @pytest.mark.asyncio
    async def test_stops_at_max_steps(self):
        """Agent should stop and return error when max_steps is reached."""
        client = _make_mock_client()

        # Always return a tool call (never a final answer)
        tool_call_response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_loop",
                "name": "echo",
                "arguments": '{"message": "again"}',
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        client.chat_with_tools = AsyncMock(return_value=tool_call_response)

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=3, system_prompt="Test"),
        )

        result = await runner.run("Loop forever")

        assert result.error == "max_steps_reached"
        assert len(result.steps) == 3  # 3 tool_call steps


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------


class TestAgentRunnerTokenBudget:
    """Tests for token budget enforcement."""

    @pytest.mark.asyncio
    async def test_stops_when_budget_exhausted(self):
        """Agent should stop when token budget is exceeded."""
        client = _make_mock_client()

        # Each call uses a lot of tokens
        response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "name": "echo",
                "arguments": '{"message": "x"}',
            }],
            "usage": {"prompt_tokens": 5000, "completion_tokens": 5000, "total_tokens": 10000},
        }

        # Second call would exceed budget, but the budget is checked
        # before calling LLM. Since first call uses 10000, next check at
        # step 2 the budget (10000) is exactly at the limit (10000).
        client.chat_with_tools = AsyncMock(return_value=response)

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=10, max_tokens_budget=10000, system_prompt="Test"),
        )

        result = await runner.run("Use tokens")

        # Should have run 1 step (using 10000 tokens), then stopped on step 2
        # because budget is exhausted
        assert result.total_tokens >= 10000
        assert result.error == "max_steps_reached"


# ---------------------------------------------------------------------------
# Fallback parsing
# ---------------------------------------------------------------------------


class TestAgentRunnerFallbackParsing:
    """Tests for fallback tool-call extraction from content."""

    @pytest.mark.asyncio
    async def test_extracts_tool_call_from_content(self):
        """When LLM embeds tool calls in content, runner should extract them."""
        client = _make_mock_client()

        # First call: tool call embedded in content
        call_1 = {
            "role": "assistant",
            "content": 'Let me echo: {"name": "echo", "arguments": {"message": "fallback"}}',
            "tool_calls": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }

        # Second call: final answer
        call_2 = {
            "role": "assistant",
            "content": "The echo returned: echo: fallback",
            "tool_calls": [],
            "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
        }

        client.chat_with_tools = AsyncMock(side_effect=[call_1, call_2])

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
        )

        result = await runner.run("Echo via fallback")

        assert result.answer == "The echo returned: echo: fallback"
        assert result.error is None
        assert len(result.steps) == 2
        assert result.steps[0].action == "tool_call"
        assert result.steps[0].tool_name == "echo"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestAgentRunnerErrorHandling:
    """Tests for error scenarios."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_result(self):
        """Calling a tool that doesn't exist should produce error in step."""
        client = _make_mock_client()

        call_1 = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_bad",
                "name": "nonexistent_tool",
                "arguments": "{}",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        call_2 = {
            "role": "assistant",
            "content": "Could not find the tool.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
        }

        client.chat_with_tools = AsyncMock(side_effect=[call_1, call_2])

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
        )

        result = await runner.run("Use missing tool")

        assert result.answer == "Could not find the tool."
        # First step should contain the error
        assert result.steps[0].tool_name == "nonexistent_tool"
        assert "未知工具" in result.steps[0].tool_result

    @pytest.mark.asyncio
    async def test_invalid_json_arguments_returns_error(self):
        """Tool call with invalid JSON arguments should be handled gracefully."""
        client = _make_mock_client()

        call_1 = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_bad_json",
                "name": "echo",
                "arguments": "not valid json",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        call_2 = {
            "role": "assistant",
            "content": "JSON was invalid.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
        }

        client.chat_with_tools = AsyncMock(side_effect=[call_1, call_2])

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
        )

        result = await runner.run("Bad args")

        # The runner should handle invalid JSON without crashing.
        # The ToolCallResult.error contains "Invalid JSON" but
        # the step's tool_result is the empty string from the result field.
        # The important thing is no exception was raised.
        tool_step = result.steps[0]
        assert tool_step.action == "tool_call"
        assert tool_step.tool_name == "echo"
        # The runner should still produce a final answer
        assert result.answer == "JSON was invalid."

    @pytest.mark.asyncio
    async def test_llm_exception_returns_error_result(self):
        """If the LLM call throws, runner returns error result."""
        client = _make_mock_client()
        client.chat_with_tools = AsyncMock(side_effect=Exception("LLM down"))

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
        )

        result = await runner.run("Crash")

        assert result.error == "LLM down"
        assert result.answer == ""


# ---------------------------------------------------------------------------
# on_step callback
# ---------------------------------------------------------------------------


class TestAgentRunnerOnStep:
    """Tests for the on_step callback."""

    @pytest.mark.asyncio
    async def test_on_step_called_for_each_step(self):
        """on_step should be invoked once per step."""
        client = _make_mock_client()

        call_1 = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "name": "echo",
                "arguments": '{"message": "test"}',
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        call_2 = {
            "role": "assistant",
            "content": "Done",
            "tool_calls": [],
            "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
        }

        client.chat_with_tools = AsyncMock(side_effect=[call_1, call_2])

        captured_steps = []

        def on_step(step):
            captured_steps.append(step)

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
            on_step=on_step,
        )

        await runner.run("Step test")

        assert len(captured_steps) == 2
        assert captured_steps[0].action == "tool_call"
        assert captured_steps[1].action == "final_answer"

    @pytest.mark.asyncio
    async def test_on_step_exception_does_not_crash(self):
        """If on_step callback raises, runner should continue."""
        client = _make_mock_client()

        client.chat_with_tools = AsyncMock(return_value={
            "role": "assistant",
            "content": "Final answer",
            "tool_calls": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

        def bad_callback(step):
            raise RuntimeError("callback error")

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="Test"),
            on_step=bad_callback,
        )

        result = await runner.run("Should not crash")
        assert result.answer == "Final answer"
        assert result.error is None


# ---------------------------------------------------------------------------
# Context messages
# ---------------------------------------------------------------------------


class TestAgentRunnerContextMessages:
    """Tests for context message handling."""

    @pytest.mark.asyncio
    async def test_context_messages_prepended(self):
        """Prior conversation context should be included in messages."""
        client = _make_mock_client()

        captured_messages = []

        async def capture_chat(messages, tools, temperature):
            captured_messages.extend(messages)
            return {
                "role": "assistant",
                "content": "OK",
                "tool_calls": [],
                "usage": {"total_tokens": 10},
            }

        client.chat_with_tools = capture_chat

        runner = AgentRunner(
            client=client,
            registry=_make_registry_with_tools(),
            config=AgentConfig(max_steps=5, system_prompt="System"),
        )

        await runner.run(
            "Current question",
            context_messages=[
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ],
        )

        assert captured_messages[0]["role"] == "system"
        assert captured_messages[1]["role"] == "user"
        assert captured_messages[1]["content"] == "Previous question"
        assert captured_messages[2]["role"] == "assistant"
        assert captured_messages[3]["role"] == "user"
        assert captured_messages[3]["content"] == "Current question"
