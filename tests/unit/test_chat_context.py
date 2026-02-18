"""Tests for chat context builders."""

import pytest

from src.chat.context import build_sql_result_context


class TestBuildSqlResultContext:
    """Tests for build_sql_result_context()."""

    def test_basic_table(self):
        rows = [(1, "AK2510034", 100), (2, "AK2510035", 200)]
        cols = ["id", "mto_number", "qty"]
        result = build_sql_result_context(rows, cols)
        assert "id" in result
        assert "AK2510034" in result
        assert "---" in result  # Separator

    def test_empty_rows(self):
        result = build_sql_result_context([], ["col1"])
        assert "无结果" in result

    def test_truncation(self):
        rows = [(i,) for i in range(100)]
        cols = ["id"]
        result = build_sql_result_context(rows, cols)
        assert "共 100 行" in result
        assert "前 50 行" in result

    def test_none_values(self):
        rows = [(1, None, "test")]
        cols = ["a", "b", "c"]
        result = build_sql_result_context(rows, cols)
        assert "| 1 |  | test |" in result
