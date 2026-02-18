"""Tests for agent tools — sql_query, schema_lookup, mto_lookup, config_lookup."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import ToolDefinition


# ---------------------------------------------------------------------------
# SQL Query Tool
# ---------------------------------------------------------------------------


class TestSqlQueryTool:
    """Tests for create_sql_query_tool."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute_read_with_columns = AsyncMock()
        return db

    @pytest.fixture
    def sql_tool(self, mock_db):
        from src.agents.tools.sql_query import create_sql_query_tool
        return create_sql_query_tool(mock_db)

    def test_tool_metadata(self, sql_tool):
        assert sql_tool.name == "sql_query"
        assert "SELECT" in sql_tool.description
        assert sql_tool.parameters["required"] == ["query"]

    @pytest.mark.asyncio
    async def test_valid_query_returns_results(self, sql_tool, mock_db):
        mock_db.execute_read_with_columns.return_value = (
            [(1, "AK2510034")],
            ["id", "mto_number"],
        )

        result = await sql_tool.handler(
            query="SELECT id, mto_number FROM cached_production_orders LIMIT 10"
        )

        assert "AK2510034" in result
        assert "id" in result

    @pytest.mark.asyncio
    async def test_invalid_sql_returns_validation_error(self, sql_tool):
        result = await sql_tool.handler(query="DROP TABLE cached_production_orders")
        assert "SQL验证失败" in result

    @pytest.mark.asyncio
    async def test_execution_error_returns_error_message(self, sql_tool, mock_db):
        mock_db.execute_read_with_columns.side_effect = Exception("no such table")

        result = await sql_tool.handler(
            query="SELECT * FROM cached_production_orders LIMIT 10"
        )

        assert "SQL执行失败" in result


# ---------------------------------------------------------------------------
# Schema Lookup Tool
# ---------------------------------------------------------------------------


class TestSchemaLookupTool:
    """Tests for create_schema_lookup_tool."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute_read = AsyncMock()
        return db

    @pytest.fixture
    def schema_tool(self, mock_db):
        from src.agents.tools.schema_lookup import create_schema_lookup_tool
        return create_schema_lookup_tool(mock_db)

    def test_tool_metadata(self, schema_tool):
        assert schema_tool.name == "schema_lookup"
        assert schema_tool.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_list_all_tables(self, schema_tool):
        result = await schema_tool.handler()
        assert "可用数据表" in result
        assert "cached_production_orders" in result

    @pytest.mark.asyncio
    async def test_specific_table_columns(self, schema_tool, mock_db):
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        mock_db.execute_read.return_value = [
            (0, "id", "INTEGER", 1, None, 1),
            (1, "mto_number", "TEXT", 0, None, 0),
            (2, "bill_no", "TEXT", 0, None, 0),
        ]

        result = await schema_tool.handler(table_name="cached_production_orders")

        assert "cached_production_orders" in result
        assert "mto_number" in result
        assert "bill_no" in result
        assert "列名" in result  # table header

    @pytest.mark.asyncio
    async def test_unknown_table_returns_error(self, schema_tool):
        result = await schema_tool.handler(table_name="forbidden_table")
        assert "不在允许列表中" in result

    @pytest.mark.asyncio
    async def test_table_not_exists_returns_message(self, schema_tool, mock_db):
        mock_db.execute_read.return_value = []

        result = await schema_tool.handler(table_name="cached_production_orders")

        assert "不存在" in result or "没有列" in result


# ---------------------------------------------------------------------------
# MTO Lookup Tool
# ---------------------------------------------------------------------------


class TestMtoLookupTool:
    """Tests for create_mto_lookup_tool."""

    @pytest.fixture
    def mock_handler(self):
        handler = MagicMock()
        handler.query = AsyncMock()
        return handler

    @pytest.fixture
    def mto_tool(self, mock_handler):
        from src.agents.tools.mto_lookup import create_mto_lookup_tool
        return create_mto_lookup_tool(mock_handler)

    def test_tool_metadata(self, mto_tool):
        assert mto_tool.name == "mto_lookup"
        assert mto_tool.parameters["required"] == ["mto_number"]

    @pytest.mark.asyncio
    async def test_valid_mto_returns_json(self, mto_tool, mock_handler):
        mock_parent = MagicMock()
        mock_parent.bill_no = "MO0001"
        mock_parent.material_code = "P001"
        mock_parent.material_name = "Product A"
        mock_parent.qty = 100

        mock_result = MagicMock()
        mock_result.parent_item = mock_parent
        mock_result.child_items = []

        mock_handler.query.return_value = mock_result

        result = await mto_tool.handler(mto_number="AK2510034")
        data = json.loads(result)

        assert data["mto_number"] == "AK2510034"
        assert data["parent_item"]["bill_no"] == "MO0001"
        assert data["child_count"] == 0

    @pytest.mark.asyncio
    async def test_unknown_mto_returns_not_found(self, mto_tool, mock_handler):
        mock_handler.query.return_value = None

        result = await mto_tool.handler(mto_number="UNKNOWN123")

        assert "未找到MTO" in result
        assert "UNKNOWN123" in result

    @pytest.mark.asyncio
    async def test_query_exception_returns_error(self, mto_tool, mock_handler):
        mock_handler.query.side_effect = Exception("DB connection lost")

        result = await mto_tool.handler(mto_number="AK2510034")

        assert "MTO查询失败" in result

    @pytest.mark.asyncio
    async def test_children_with_metrics(self, mto_tool, mock_handler):
        mock_parent = MagicMock()
        mock_parent.bill_no = "MO0001"
        mock_parent.material_code = "P001"
        mock_parent.material_name = "Product A"
        mock_parent.qty = 100

        mock_metric = MagicMock()
        mock_metric.value = 0.85
        mock_metric.status = "in_progress"

        mock_child = MagicMock()
        mock_child.material_code = "C001"
        mock_child.material_name = "Child 1"
        mock_child.metrics = {"fulfillment_rate": mock_metric}

        mock_result = MagicMock()
        mock_result.parent_item = mock_parent
        mock_result.child_items = [mock_child]

        mock_handler.query.return_value = mock_result

        result = await mto_tool.handler(mto_number="AK2510034")
        data = json.loads(result)

        assert data["child_count"] == 1
        assert "fulfillment_rate" in data["children_summary"][0]["metrics"]


# ---------------------------------------------------------------------------
# Config Lookup Tool
# ---------------------------------------------------------------------------


class TestConfigLookupTool:
    """Tests for create_config_lookup_tool."""

    @pytest.fixture
    def mto_config(self):
        from src.mto_config.mto_config import MTOConfig
        config_path = "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2/config/mto_config.json"
        return MTOConfig(config_path)

    @pytest.fixture
    def config_tool(self, mto_config):
        from src.agents.tools.config_lookup import create_config_lookup_tool
        return create_config_lookup_tool(mto_config)

    def test_tool_metadata(self, config_tool):
        assert config_tool.name == "config_lookup"
        assert config_tool.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_overview_section(self, config_tool):
        result = await config_tool.handler()
        data = json.loads(result)

        assert "material_classes" in data
        assert "receipt_sources" in data
        assert len(data["material_classes"]) >= 3

    @pytest.mark.asyncio
    async def test_material_classes_section(self, config_tool):
        result = await config_tool.handler(section="material_classes")
        data = json.loads(result)

        assert isinstance(data, list)
        assert len(data) >= 3
        ids = [mc["id"] for mc in data]
        assert "finished_goods" in ids

    @pytest.mark.asyncio
    async def test_specific_class_id(self, config_tool):
        result = await config_tool.handler(section="finished_goods")
        data = json.loads(result)

        assert data["id"] == "finished_goods"
        assert "columns" in data
        assert "item_fields" in data

    @pytest.mark.asyncio
    async def test_unknown_section_returns_error(self, config_tool):
        result = await config_tool.handler(section="nonexistent_section")
        assert "未知配置节" in result
