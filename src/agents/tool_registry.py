"""Tool registry — central lookup for agent tools."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.agents.base import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for agent tools.

    Tools are registered by name and can be looked up for execution.
    The registry also produces the OpenAI-format tool list for LLM calls.

    Usage:
        registry = ToolRegistry()
        registry.register(my_tool)
        tool = registry.get("my_tool")
        openai_tools = registry.to_openai_tools()
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool. Overwrites if name already exists."""
        if tool.name in self._tools:
            logger.warning("Overwriting tool: %s", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def register_many(self, tools: List[ToolDefinition]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Look up a tool by name."""
        return self._tools.get(name)

    def to_openai_tools(self) -> List[Dict]:
        """Convert all registered tools to OpenAI function-calling format."""
        return [t.to_openai_tool() for t in self._tools.values()]

    @property
    def tool_names(self) -> List[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
