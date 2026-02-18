"""Reasoning agent — generates SQL, executes queries, self-corrects, and answers.

Receives the data plan from RetrievalAgent and uses sql_query and mto_lookup
tools to fetch data and produce a natural-language answer.
"""

import logging
from typing import Callable, List, Optional

from src.agents.base import (
    AgentBase,
    AgentConfig,
    AgentLLMClient,
    AgentResult,
    AgentStep,
    ToolDefinition,
)
from src.agents.runner import AgentRunner
from src.agents.tool_registry import ToolRegistry
from src.agents.chat.prompts import REASONING_AGENT_PROMPT

logger = logging.getLogger(__name__)


class ReasoningAgent(AgentBase):
    """Generates SQL, executes, self-corrects on errors, and produces answers.

    Tools: sql_query, mto_lookup
    Max steps: 5 (generate -> execute -> retry -> retry -> answer)
    """

    def __init__(
        self,
        sql_tool: ToolDefinition,
        mto_tool: ToolDefinition,
        llm_client: AgentLLMClient,
        max_steps: int = 5,
    ) -> None:
        config = AgentConfig(
            max_steps=max_steps,
            temperature=0.1,
            system_prompt=REASONING_AGENT_PROMPT,
        )
        super().__init__(name="reasoning_agent", config=config)
        self._sql_tool = sql_tool
        self._mto_tool = mto_tool
        self._llm_client = llm_client

    def get_tools(self) -> List[ToolDefinition]:
        return [self._sql_tool, self._mto_tool]

    def get_system_prompt(self) -> str:
        return self.config.system_prompt

    async def run(
        self,
        question: str,
        data_plan: str,
        mto_context: Optional[str] = None,
        on_step: Optional[Callable[[AgentStep], None]] = None,
    ) -> AgentResult:
        """Run the reasoning agent to answer the user's question.

        Args:
            question: The user's original question.
            data_plan: The data retrieval plan from RetrievalAgent.
            mto_context: Optional MTO context string.
            on_step: Optional callback for each reasoning step (for SSE).

        Returns:
            AgentResult whose ``answer`` is the final response.
        """
        registry = ToolRegistry()
        registry.register_many(self.get_tools())

        runner = AgentRunner(
            client=self._llm_client,
            registry=registry,
            config=self.config,
            on_step=on_step,
        )

        # Build the user message with plan context
        parts = []
        if mto_context:
            parts.append(f"[当前MTO上下文]\n{mto_context}")
        parts.append(f"[数据检索计划]\n{data_plan}")
        parts.append(f"[用户问题]\n{question}")
        user_msg = "\n\n".join(parts)

        result = await runner.run(user_msg)
        logger.info(
            "ReasoningAgent completed: %d steps, %d tokens, error=%s",
            len(result.steps),
            result.total_tokens,
            result.error,
        )
        return result
