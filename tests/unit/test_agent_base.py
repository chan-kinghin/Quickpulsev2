"""Tests for agent base abstractions — models, configs, LLM client, and parsing."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import (
    AgentConfig,
    AgentLLMClient,
    AgentResult,
    AgentStep,
    ToolCallResult,
    ToolDefinition,
    extract_tool_calls_from_content,
)
from src.config import DeepSeekConfig
from src.exceptions import ChatConnectionError, ChatRateLimitError


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    """Tests for ToolDefinition dataclass and to_openai_tool()."""

    def test_to_openai_tool_format(self):
        async def dummy(**kwargs):
            return "ok"

        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=dummy,
        )
        result = tool.to_openai_tool()

        assert result["type"] == "function"
        assert result["function"]["name"] == "test_tool"
        assert result["function"]["description"] == "A test tool"
        assert result["function"]["parameters"]["required"] == ["query"]

    def test_to_openai_tool_has_three_keys(self):
        async def dummy(**kwargs):
            return "ok"

        tool = ToolDefinition(
            name="t",
            description="d",
            parameters={"type": "object", "properties": {}},
            handler=dummy,
        )
        result = tool.to_openai_tool()

        assert set(result.keys()) == {"type", "function"}
        assert set(result["function"].keys()) == {"name", "description", "parameters"}


# ---------------------------------------------------------------------------
# extract_tool_calls_from_content (regex fallback)
# ---------------------------------------------------------------------------


class TestExtractToolCallsFromContent:
    """Tests for the fallback regex tool-call parser."""

    def test_extracts_single_tool_call(self):
        content = 'I will query the database: {"name": "sql_query", "arguments": {"query": "SELECT 1"}}'
        results = extract_tool_calls_from_content(content)
        assert len(results) == 1
        assert results[0]["name"] == "sql_query"
        assert results[0]["id"] == "fallback_sql_query_0"
        args = json.loads(results[0]["arguments"])
        assert args["query"] == "SELECT 1"

    def test_extracts_multiple_tool_calls(self):
        content = (
            '{"name": "tool_a", "arguments": {"x": 1}} '
            '{"name": "tool_b", "arguments": {"y": 2}}'
        )
        results = extract_tool_calls_from_content(content)
        assert len(results) == 2
        assert results[0]["name"] == "tool_a"
        assert results[1]["name"] == "tool_b"

    def test_returns_empty_for_no_match(self):
        content = "No tool calls here, just a normal response."
        results = extract_tool_calls_from_content(content)
        assert results == []

    def test_returns_empty_for_empty_string(self):
        results = extract_tool_calls_from_content("")
        assert results == []

    def test_skips_invalid_json_arguments(self):
        content = '{"name": "bad_tool", "arguments": {invalid json}}'
        results = extract_tool_calls_from_content(content)
        assert results == []

    def test_fallback_ids_are_sequential(self):
        content = (
            '{"name": "t", "arguments": {"a": 1}} '
            '{"name": "t", "arguments": {"b": 2}}'
        )
        results = extract_tool_calls_from_content(content)
        assert results[0]["id"] == "fallback_t_0"
        assert results[1]["id"] == "fallback_t_1"


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------


class TestAgentConfig:
    """Tests for AgentConfig default values."""

    def test_default_values(self):
        config = AgentConfig()
        assert config.max_steps == 5
        assert config.max_tokens_budget == 32000
        assert config.temperature == 0.1
        assert config.system_prompt == ""

    def test_custom_values(self):
        config = AgentConfig(
            max_steps=10,
            max_tokens_budget=64000,
            temperature=0.5,
            system_prompt="You are a test agent.",
        )
        assert config.max_steps == 10
        assert config.max_tokens_budget == 64000
        assert config.temperature == 0.5
        assert config.system_prompt == "You are a test agent."


# ---------------------------------------------------------------------------
# AgentResult & AgentStep
# ---------------------------------------------------------------------------


class TestAgentResult:
    """Tests for AgentResult and AgentStep dataclasses."""

    def test_default_result(self):
        result = AgentResult(answer="Hello")
        assert result.answer == "Hello"
        assert result.steps == []
        assert result.total_tokens == 0
        assert result.error is None

    def test_result_with_steps(self):
        step = AgentStep(
            step_number=1,
            action="tool_call",
            tool_name="sql_query",
            tool_args={"query": "SELECT 1"},
            tool_result="1",
        )
        result = AgentResult(answer="done", steps=[step], total_tokens=500)
        assert len(result.steps) == 1
        assert result.steps[0].tool_name == "sql_query"


class TestToolCallResult:
    """Tests for ToolCallResult."""

    def test_successful_result(self):
        r = ToolCallResult(
            tool_name="sql_query",
            tool_call_id="call_1",
            arguments={"query": "SELECT 1"},
            result="| result |\n| 1 |",
        )
        assert r.error is None
        assert "result" in r.result

    def test_error_result(self):
        r = ToolCallResult(
            tool_name="unknown",
            tool_call_id="call_2",
            arguments={},
            result="",
            error="Tool not found",
        )
        assert r.error == "Tool not found"


# ---------------------------------------------------------------------------
# AgentLLMClient
# ---------------------------------------------------------------------------


class TestAgentLLMClient:
    """Tests for AgentLLMClient with mocked AsyncOpenAI."""

    @pytest.fixture
    def deepseek_config(self):
        return DeepSeekConfig(
            api_key="test-key",
            base_url="https://api.test.com",
            model="test-model",
            max_tokens=1024,
            temperature=0.1,
            timeout_seconds=30,
        )

    @pytest.mark.asyncio
    async def test_chat_with_tools_returns_content(self, deepseek_config):
        client = AgentLLMClient(deepseek_config)

        mock_msg = MagicMock()
        mock_msg.content = "Here is the answer."
        mock_msg.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_choice = MagicMock()
        mock_choice.message = mock_msg

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )

        assert result["role"] == "assistant"
        assert result["content"] == "Here is the answer."
        assert result["tool_calls"] == []
        assert result["usage"]["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_chat_with_tools_returns_tool_calls(self, deepseek_config):
        client = AgentLLMClient(deepseek_config)

        mock_tc = MagicMock()
        mock_tc.id = "call_123"
        mock_tc.function.name = "sql_query"
        mock_tc.function.arguments = '{"query": "SELECT 1"}'

        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tc]

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 25
        mock_usage.total_tokens = 75

        mock_choice = MagicMock()
        mock_choice.message = mock_msg

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await client.chat_with_tools(
            messages=[{"role": "user", "content": "query db"}],
            tools=[{"type": "function", "function": {"name": "sql_query"}}],
        )

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "sql_query"
        assert result["tool_calls"][0]["id"] == "call_123"

    @pytest.mark.asyncio
    async def test_rate_limit_raises_chat_rate_limit_error(self, deepseek_config):
        from openai import RateLimitError

        client = AgentLLMClient(deepseek_config)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        client._client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit",
                response=mock_response,
                body=None,
            )
        )

        with pytest.raises(ChatRateLimitError):
            await client.chat_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )

    @pytest.mark.asyncio
    async def test_connection_error_raises_chat_connection_error(self, deepseek_config):
        from openai import APIConnectionError

        client = AgentLLMClient(deepseek_config)

        client._client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ChatConnectionError):
            await client.chat_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )

    @pytest.mark.asyncio
    async def test_close_calls_underlying_client(self, deepseek_config):
        client = AgentLLMClient(deepseek_config)
        client._client.close = AsyncMock()

        await client.close()

        client._client.close.assert_called_once()
