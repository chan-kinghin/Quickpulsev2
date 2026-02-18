"""Retrieval agent — explores schema + config to build a data retrieval plan.

Uses schema_lookup and config_lookup tools to understand what data is
available, then produces a structured plan for the ReasoningAgent.
"""

import logging
from typing import List, Optional

from src.agents.base import AgentBase, AgentConfig, AgentLLMClient, AgentResult, ToolDefinition
from src.agents.runner import AgentRunner
from src.agents.tool_registry import ToolRegistry
from src.agents.chat.prompts import RETRIEVAL_AGENT_PROMPT

logger = logging.getLogger(__name__)


class RetrievalAgent(AgentBase):
    """Explores DB schema and MTO config to produce a data retrieval plan.

    Tools: schema_lookup, config_lookup
    Max steps: 3 (explore -> verify -> plan)
    """

    def __init__(
        self,
        schema_tool: ToolDefinition,
        config_tool: ToolDefinition,
        llm_client: AgentLLMClient,
        max_steps: int = 6,
    ) -> None:
        config = AgentConfig(
            max_steps=max_steps,
            temperature=0.1,
            system_prompt=RETRIEVAL_AGENT_PROMPT,
        )
        super().__init__(name="retrieval_agent", config=config)
        self._schema_tool = schema_tool
        self._config_tool = config_tool
        self._llm_client = llm_client

    def get_tools(self) -> List[ToolDefinition]:
        return [self._schema_tool, self._config_tool]

    def get_system_prompt(self) -> str:
        return self.config.system_prompt

    async def run(
        self,
        question: str,
        mto_context: Optional[str] = None,
    ) -> AgentResult:
        """Run the retrieval agent to produce a data plan.

        Args:
            question: The user's question.
            mto_context: Optional MTO context string to prepend.

        Returns:
            AgentResult whose ``answer`` is the data retrieval plan.
        """
        registry = ToolRegistry()
        registry.register_many(self.get_tools())

        runner = AgentRunner(
            client=self._llm_client,
            registry=registry,
            config=self.config,
        )

        user_msg = question
        if mto_context:
            user_msg = f"[当前MTO上下文]\n{mto_context}\n\n[用户问题]\n{question}"

        result = await runner.run(user_msg)
        logger.info(
            "RetrievalAgent completed: %d steps, %d tokens",
            len(result.steps),
            result.total_tokens,
        )
        return result
