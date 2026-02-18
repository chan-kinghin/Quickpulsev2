"""Tests for Phase 2 agent chat — RetrievalAgent, ReasoningAgent, orchestrator."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import (
    AgentConfig,
    AgentLLMClient,
    AgentResult,
    AgentStep,
    ToolDefinition,
)
from src.agents.chat.prompts import RETRIEVAL_AGENT_PROMPT, REASONING_AGENT_PROMPT
from src.agents.chat.retrieval_agent import RetrievalAgent
from src.agents.chat.reasoning_agent import ReasoningAgent
from src.agents.chat.orchestrator import AgentChatOrchestrator


def _make_tool(name: str) -> ToolDefinition:
    """Create a minimal ToolDefinition for testing."""

    async def handler(**kwargs):
        return f"{name} result"

    return ToolDefinition(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )


def _make_mock_llm_client():
    """Create a mock AgentLLMClient."""
    client = MagicMock(spec=AgentLLMClient)
    return client


# ---------------------------------------------------------------------------
# RetrievalAgent
# ---------------------------------------------------------------------------


class TestRetrievalAgent:
    """Tests for RetrievalAgent."""

    def test_get_tools_returns_schema_and_config(self):
        schema_tool = _make_tool("schema_lookup")
        config_tool = _make_tool("config_lookup")
        client = _make_mock_llm_client()

        agent = RetrievalAgent(
            schema_tool=schema_tool,
            config_tool=config_tool,
            llm_client=client,
        )

        tools = agent.get_tools()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "schema_lookup" in names
        assert "config_lookup" in names

    def test_system_prompt_is_retrieval_prompt(self):
        agent = RetrievalAgent(
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            llm_client=_make_mock_llm_client(),
        )
        assert agent.get_system_prompt() == RETRIEVAL_AGENT_PROMPT

    def test_name_is_retrieval_agent(self):
        agent = RetrievalAgent(
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            llm_client=_make_mock_llm_client(),
        )
        assert agent.name == "retrieval_agent"

    def test_default_max_steps_is_6(self):
        agent = RetrievalAgent(
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            llm_client=_make_mock_llm_client(),
        )
        assert agent.config.max_steps == 6

    @pytest.mark.asyncio
    async def test_run_produces_data_plan(self):
        """RetrievalAgent.run should return an AgentResult with a plan."""
        client = _make_mock_llm_client()
        client.chat_with_tools = AsyncMock(return_value={
            "role": "assistant",
            "content": "Plan: Query cached_production_orders for MTO data.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
        })

        agent = RetrievalAgent(
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            llm_client=client,
        )

        result = await agent.run("What is AK2510034?")
        assert result.answer == "Plan: Query cached_production_orders for MTO data."
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_with_mto_context(self):
        """MTO context should be prepended to the user message."""
        client = _make_mock_llm_client()

        captured_user_msg = []

        async def capture(messages, tools, temperature):
            # The user message is the last one
            for m in messages:
                if m["role"] == "user":
                    captured_user_msg.append(m["content"])
            return {
                "role": "assistant",
                "content": "Plan with context",
                "tool_calls": [],
                "usage": {"total_tokens": 20},
            }

        client.chat_with_tools = capture

        agent = RetrievalAgent(
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            llm_client=client,
        )

        await agent.run("What about the BOM?", mto_context="MTO: AK2510034")

        assert len(captured_user_msg) == 1
        assert "AK2510034" in captured_user_msg[0]
        assert "BOM" in captured_user_msg[0]


# ---------------------------------------------------------------------------
# ReasoningAgent
# ---------------------------------------------------------------------------


class TestReasoningAgent:
    """Tests for ReasoningAgent."""

    def test_get_tools_returns_sql_and_mto(self):
        sql_tool = _make_tool("sql_query")
        mto_tool = _make_tool("mto_lookup")
        client = _make_mock_llm_client()

        agent = ReasoningAgent(
            sql_tool=sql_tool,
            mto_tool=mto_tool,
            llm_client=client,
        )

        tools = agent.get_tools()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "sql_query" in names
        assert "mto_lookup" in names

    def test_system_prompt_is_reasoning_prompt(self):
        agent = ReasoningAgent(
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
            llm_client=_make_mock_llm_client(),
        )
        assert agent.get_system_prompt() == REASONING_AGENT_PROMPT

    def test_name_is_reasoning_agent(self):
        agent = ReasoningAgent(
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
            llm_client=_make_mock_llm_client(),
        )
        assert agent.name == "reasoning_agent"

    def test_default_max_steps_is_5(self):
        agent = ReasoningAgent(
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
            llm_client=_make_mock_llm_client(),
        )
        assert agent.config.max_steps == 5

    @pytest.mark.asyncio
    async def test_run_produces_answer(self):
        """ReasoningAgent.run should return an AgentResult with an answer."""
        client = _make_mock_llm_client()
        client.chat_with_tools = AsyncMock(return_value={
            "role": "assistant",
            "content": "MTO AK2510034 has 5 child items, all 100% complete.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
        })

        agent = ReasoningAgent(
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
            llm_client=client,
        )

        result = await agent.run(
            question="What is the status of AK2510034?",
            data_plan="Query cached_production_orders table.",
        )

        assert "AK2510034" in result.answer
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_includes_plan_in_user_message(self):
        """The data plan should be included in the user message."""
        client = _make_mock_llm_client()

        captured_content = []

        async def capture(messages, tools, temperature):
            for m in messages:
                if m["role"] == "user":
                    captured_content.append(m["content"])
            return {
                "role": "assistant",
                "content": "Answer",
                "tool_calls": [],
                "usage": {"total_tokens": 10},
            }

        client.chat_with_tools = capture

        agent = ReasoningAgent(
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
            llm_client=client,
        )

        await agent.run(
            question="Status?",
            data_plan="Use cached_production_orders",
        )

        assert len(captured_content) == 1
        assert "数据检索计划" in captured_content[0]
        assert "cached_production_orders" in captured_content[0]


# ---------------------------------------------------------------------------
# AgentChatOrchestrator
# ---------------------------------------------------------------------------


class TestAgentChatOrchestrator:
    """Tests for the orchestrator coordinating retrieval + reasoning agents."""

    @pytest.mark.asyncio
    async def test_run_emits_expected_events(self):
        """Orchestrator should emit agent_step, data_plan, token, done events."""
        client = _make_mock_llm_client()

        # Retrieval: immediate answer (plan)
        # Reasoning: immediate answer
        call_count = [0]

        async def mock_chat(messages, tools, temperature):
            call_count[0] += 1
            if call_count[0] == 1:
                # Retrieval agent produces plan
                return {
                    "role": "assistant",
                    "content": "Plan: check production_orders table",
                    "tool_calls": [],
                    "usage": {"total_tokens": 20},
                }
            else:
                # Reasoning agent produces answer
                return {
                    "role": "assistant",
                    "content": "MTO has 3 items, all complete.",
                    "tool_calls": [],
                    "usage": {"total_tokens": 30},
                }

        client.chat_with_tools = mock_chat

        orchestrator = AgentChatOrchestrator(
            llm_client=client,
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
        )

        events = []

        async def on_event(event):
            events.append(event)

        await orchestrator.run(
            question="Status of AK2510034?",
            on_event=on_event,
        )

        event_types = [e["type"] for e in events]

        # Must have agent_step, data_plan, token, done
        assert "agent_step" in event_types
        assert "data_plan" in event_types
        assert "token" in event_types
        assert "done" in event_types
        # "done" must be the last event
        assert event_types[-1] == "done"

    @pytest.mark.asyncio
    async def test_run_emits_error_when_retrieval_fails(self):
        """When retrieval agent fails, an error event should be emitted."""
        client = _make_mock_llm_client()
        client.chat_with_tools = AsyncMock(side_effect=Exception("LLM down"))

        orchestrator = AgentChatOrchestrator(
            llm_client=client,
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
        )

        events = []

        async def on_event(event):
            events.append(event)

        await orchestrator.run(
            question="Fail",
            on_event=on_event,
        )

        event_types = [e["type"] for e in events]
        assert "error" in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    async def test_run_without_on_event(self):
        """Orchestrator should work without an on_event callback."""
        client = _make_mock_llm_client()
        client.chat_with_tools = AsyncMock(return_value={
            "role": "assistant",
            "content": "Plan and answer combined.",
            "tool_calls": [],
            "usage": {"total_tokens": 20},
        })

        orchestrator = AgentChatOrchestrator(
            llm_client=client,
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
        )

        # Should not raise
        await orchestrator.run(question="Test", on_event=None)

    @pytest.mark.asyncio
    async def test_mto_context_passed_to_agents(self):
        """MTO context should be passed through to both agents."""
        client = _make_mock_llm_client()

        captured_messages = []

        async def capture(messages, tools, temperature):
            for m in messages:
                if m["role"] == "user":
                    captured_messages.append(m["content"])
            return {
                "role": "assistant",
                "content": "Result",
                "tool_calls": [],
                "usage": {"total_tokens": 10},
            }

        client.chat_with_tools = capture

        orchestrator = AgentChatOrchestrator(
            llm_client=client,
            schema_tool=_make_tool("schema_lookup"),
            config_tool=_make_tool("config_lookup"),
            sql_tool=_make_tool("sql_query"),
            mto_tool=_make_tool("mto_lookup"),
        )

        events = []
        await orchestrator.run(
            question="Status?",
            mto_context="用户正在查看 MTO: AK2510034",
            on_event=lambda e: events.append(e),
        )

        # At least the retrieval agent should receive MTO context
        assert any("AK2510034" in msg for msg in captured_messages)
