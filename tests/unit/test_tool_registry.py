"""Tests for ToolRegistry — registration, lookup, and OpenAI tool format."""

import logging

import pytest

from src.agents.base import ToolDefinition
from src.agents.tool_registry import ToolRegistry


def _make_tool(name: str) -> ToolDefinition:
    """Create a simple ToolDefinition for testing."""

    async def handler(**kwargs):
        return f"{name} executed"

    return ToolDefinition(
        name=name,
        description=f"Description of {name}",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )


class TestToolRegistryRegister:
    """Tests for register and register_many."""

    def test_register_single_tool(self):
        registry = ToolRegistry()
        tool = _make_tool("sql_query")
        registry.register(tool)

        assert len(registry) == 1
        assert "sql_query" in registry

    def test_register_many_tools(self):
        registry = ToolRegistry()
        tools = [_make_tool("a"), _make_tool("b"), _make_tool("c")]
        registry.register_many(tools)

        assert len(registry) == 3
        assert registry.tool_names == ["a", "b", "c"]

    def test_overwrite_warning(self, caplog):
        registry = ToolRegistry()
        tool1 = _make_tool("dup")
        tool2 = _make_tool("dup")

        registry.register(tool1)
        with caplog.at_level(logging.WARNING):
            registry.register(tool2)

        assert "Overwriting tool: dup" in caplog.text

    def test_overwrite_replaces_tool(self):
        registry = ToolRegistry()
        tool1 = _make_tool("x")
        tool2 = ToolDefinition(
            name="x",
            description="New description",
            parameters={"type": "object", "properties": {}},
            handler=tool1.handler,
        )

        registry.register(tool1)
        registry.register(tool2)

        assert registry.get("x").description == "New description"


class TestToolRegistryGet:
    """Tests for get and __contains__."""

    def test_get_existing_tool(self):
        registry = ToolRegistry()
        tool = _make_tool("my_tool")
        registry.register(tool)

        result = registry.get("my_tool")
        assert result is tool

    def test_get_nonexistent_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("missing") is None

    def test_contains_existing(self):
        registry = ToolRegistry()
        registry.register(_make_tool("present"))
        assert "present" in registry

    def test_contains_missing(self):
        registry = ToolRegistry()
        assert "absent" not in registry


class TestToolRegistryLen:
    """Tests for __len__."""

    def test_empty_registry(self):
        registry = ToolRegistry()
        assert len(registry) == 0

    def test_after_multiple_registers(self):
        registry = ToolRegistry()
        for i in range(5):
            registry.register(_make_tool(f"tool_{i}"))
        assert len(registry) == 5


class TestToolRegistryToOpenaiTools:
    """Tests for to_openai_tools conversion."""

    def test_to_openai_tools_format(self):
        registry = ToolRegistry()
        registry.register(_make_tool("alpha"))
        registry.register(_make_tool("beta"))

        tools = registry.to_openai_tools()
        assert len(tools) == 2
        assert all(t["type"] == "function" for t in tools)
        names = [t["function"]["name"] for t in tools]
        assert "alpha" in names
        assert "beta" in names

    def test_empty_registry_returns_empty_list(self):
        registry = ToolRegistry()
        assert registry.to_openai_tools() == []


class TestToolRegistryToolNames:
    """Tests for tool_names property."""

    def test_tool_names_returns_list(self):
        registry = ToolRegistry()
        registry.register(_make_tool("x"))
        registry.register(_make_tool("y"))

        names = registry.tool_names
        assert isinstance(names, list)
        assert set(names) == {"x", "y"}

    def test_tool_names_empty(self):
        registry = ToolRegistry()
        assert registry.tool_names == []
