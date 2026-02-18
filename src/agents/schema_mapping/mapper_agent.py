"""Schema mapper agent — orchestrates field discovery, comparison, and reporting.

Extends AgentBase to provide a complete schema mapping workflow:
1. Discover available Kingdee fields for a material class
2. Run multi-signal comparison via OntologyComparator (RRF)
3. Optionally validate top matches via LLM
4. Generate reports and persist suggestions

This is an admin-only offline tool — not exposed to end users.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.base import AgentBase, AgentConfig, AgentLLMClient, ToolDefinition
from src.agents.schema_mapping.comparator import MappingSuggestion, OntologyComparator
from src.agents.schema_mapping.discovery import KingdeeFieldDiscovery
from src.agents.schema_mapping.report import MappingReport
from src.database.connection import Database
from src.mto_config.mto_config import MTOConfig

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是金蝶K3Cloud ERP的Schema映射专家。

你的任务是分析金蝶ERP字段，将它们与语义角色（demand_field、fulfilled_field、picking_field）对齐。

工作流程:
1. 使用 kingdee_discovery 工具发现可用字段
2. 使用 config_lookup 工具查看当前配置
3. 分析字段含义，建议最佳映射

注意事项:
- demand_field = 需求量/订单数量（如 FQty）
- fulfilled_field = 已完成量/实际入库数量（如 FRealQty）
- picking_field = 领料量/实际发料数量（如 FActualQty）
- 每个物料类别（成品/自制/外购）有不同的字段来源
"""


class SchemaMapperAgent(AgentBase):
    """Agent that maps Kingdee fields to semantic roles.

    Orchestrates the full mapping pipeline:
    discovery -> comparison (with RRF) -> LLM validation -> reporting.

    Usage:
        agent = SchemaMapperAgent(mto_config=config, db=db, llm_client=client)
        suggestions = await agent.map_schema("finished_goods")
        report = agent.generate_report(suggestions)
    """

    def __init__(
        self,
        mto_config: MTOConfig,
        db: Optional[Database] = None,
        llm_client: Optional[AgentLLMClient] = None,
    ) -> None:
        super().__init__(
            name="schema_mapper",
            config=AgentConfig(
                max_steps=5,
                temperature=0.1,
                system_prompt=_SYSTEM_PROMPT,
            ),
        )
        self._mto_config = mto_config
        self._db = db
        self._llm_client = llm_client
        self._discovery = KingdeeFieldDiscovery(mto_config, db)
        self._comparator = OntologyComparator(llm_client)
        self._report = MappingReport()

    def get_tools(self) -> List[ToolDefinition]:
        """Return tools available to this agent."""
        from src.agents.tools.config_lookup import create_config_lookup_tool
        from src.agents.tools.kingdee_discovery import create_kingdee_discovery_tool

        tools = [
            create_config_lookup_tool(self._mto_config),
            create_kingdee_discovery_tool(self._discovery),
        ]
        if self._db:
            from src.agents.tools.schema_lookup import create_schema_lookup_tool
            tools.append(create_schema_lookup_tool(self._db))
        return tools

    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        return _SYSTEM_PROMPT

    async def map_schema(
        self, material_class_id: str
    ) -> List[MappingSuggestion]:
        """Run the full schema mapping pipeline for one material class.

        Steps:
        1. Discover all known fields for the class
        2. Get the semantic config from MTOConfig
        3. Run OntologyComparator with all 3 signals + RRF
        4. Return ranked suggestions

        Args:
            material_class_id: e.g. "finished_goods", "self_made", "purchased"

        Returns:
            List of MappingSuggestion sorted by confidence desc.
        """
        logger.info("Starting schema mapping for class: %s", material_class_id)

        # 1. Discover fields
        discovered = await self._discovery.discover_fields(material_class_id)
        if not discovered:
            logger.warning("No fields discovered for %s", material_class_id)
            return []

        logger.info(
            "Discovered %d fields for %s", len(discovered), material_class_id
        )

        # 2. Get semantic config
        mc = self._find_class(material_class_id)
        if not mc:
            logger.error("Material class '%s' not found", material_class_id)
            return []

        semantic_config = mc.semantic

        # 3. Run comparison
        suggestions = await self._comparator.compare(
            discovered, semantic_config, material_class_id
        )

        logger.info(
            "Generated %d mapping suggestions for %s",
            len(suggestions),
            material_class_id,
        )

        return suggestions

    async def map_all_classes(self) -> Dict[str, List[MappingSuggestion]]:
        """Run schema mapping for all configured material classes.

        Returns:
            Dict mapping class_id to its suggestions list.
        """
        results: Dict[str, List[MappingSuggestion]] = {}
        for mc in self._mto_config.material_classes:
            results[mc.id] = await self.map_schema(mc.id)
        return results

    def generate_report(
        self,
        suggestions: List[MappingSuggestion],
        title: Optional[str] = None,
    ) -> str:
        """Generate a markdown report from mapping suggestions."""
        return self._report.generate_report(suggestions, title)

    def generate_diff(
        self,
        suggestions: List[MappingSuggestion],
    ) -> str:
        """Generate a diff report against current configuration.

        Reads the current mto_config.json to compare against.
        """
        config_path = self._mto_config._config_path
        with open(config_path, encoding="utf-8") as f:
            current_config = json.load(f)
        return self._report.generate_diff(suggestions, current_config)

    async def persist_suggestions(
        self,
        suggestions: List[MappingSuggestion],
    ) -> int:
        """Persist mapping suggestions to the database.

        Requires a database connection. Creates the table if needed.

        Args:
            suggestions: Suggestions to store.

        Returns:
            Number of rows inserted.
        """
        if not self._db:
            logger.warning("No database connection — cannot persist suggestions")
            return 0

        # Ensure table exists
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        # Execute each statement separately (executescript not available via execute_write)
        for stmt in schema_sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._db.execute_write(stmt)

        # Insert suggestions
        count = 0
        for s in suggestions:
            await self._db.execute_write(
                """INSERT INTO agent_mapping_suggestions
                   (kingdee_field, semantic_role, material_class,
                    confidence, reasoning, match_signals)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    s.kingdee_field,
                    s.semantic_role,
                    s.material_class,
                    s.confidence,
                    s.reasoning,
                    json.dumps(s.match_signals, ensure_ascii=False),
                ],
            )
            count += 1

        logger.info("Persisted %d mapping suggestions to database", count)
        return count

    def _find_class(self, class_id: str):
        """Look up a MaterialClassConfig by ID."""
        for mc in self._mto_config.material_classes:
            if mc.id == class_id:
                return mc
        return None
