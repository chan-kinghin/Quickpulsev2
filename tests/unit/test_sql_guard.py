"""Tests for SQL safety validation."""

import pytest

from src.chat.sql_guard import validate_sql, ALLOWED_TABLES
from src.exceptions import ChatSQLError


class TestValidateSQL:
    """Tests for validate_sql()."""

    def test_simple_select(self):
        result = validate_sql("SELECT * FROM cached_production_orders")
        assert result == "SELECT * FROM cached_production_orders LIMIT 100"

    def test_select_with_where(self):
        sql = "SELECT mto_number, bill_no FROM cached_production_orders WHERE mto_number = 'AK2510034'"
        result = validate_sql(sql)
        assert "WHERE mto_number" in result
        assert "LIMIT 100" in result

    def test_select_with_existing_limit(self):
        sql = "SELECT * FROM cached_production_orders LIMIT 50"
        result = validate_sql(sql)
        assert result == "SELECT * FROM cached_production_orders LIMIT 50"

    def test_select_with_join(self):
        sql = (
            "SELECT a.mto_number, b.material_code "
            "FROM cached_production_orders a "
            "JOIN cached_production_bom b ON a.bill_no = b.mo_bill_no"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_cte_query_allowed(self):
        sql = (
            "WITH mto_counts AS (SELECT mto_number, COUNT(*) as cnt "
            "FROM cached_production_orders GROUP BY mto_number) "
            "SELECT * FROM mto_counts"
        )
        result = validate_sql(sql)
        assert result.startswith("WITH")
        assert "LIMIT 100" in result

    def test_all_allowed_tables(self):
        for table in ALLOWED_TABLES:
            result = validate_sql(f"SELECT COUNT(*) FROM {table}")
            assert "LIMIT 100" in result

    # === Blocked operations ===

    def test_insert_blocked(self):
        with pytest.raises(ChatSQLError):
            validate_sql("INSERT INTO cached_production_orders VALUES (1, 'x')")

    def test_update_blocked(self):
        with pytest.raises(ChatSQLError):
            validate_sql("UPDATE cached_production_orders SET mto_number = 'x'")

    def test_delete_blocked(self):
        with pytest.raises(ChatSQLError):
            validate_sql("DELETE FROM cached_production_orders")

    def test_drop_blocked(self):
        with pytest.raises(ChatSQLError):
            validate_sql("DROP TABLE cached_production_orders")

    def test_pragma_blocked(self):
        with pytest.raises(ChatSQLError):
            validate_sql("PRAGMA table_info(cached_production_orders)")

    def test_attach_blocked(self):
        with pytest.raises(ChatSQLError):
            validate_sql("ATTACH DATABASE '/tmp/evil.db' AS evil")

    def test_forbidden_keyword_in_subquery(self):
        """Ensure forbidden keywords caught even inside a SELECT wrapper."""
        with pytest.raises(ChatSQLError, match="DROP"):
            validate_sql("SELECT DROP FROM cached_production_orders")

    # === Comment stripping ===

    def test_line_comment_stripped(self):
        sql = "SELECT * FROM cached_production_orders -- this is safe"
        result = validate_sql(sql)
        assert "--" not in result

    def test_block_comment_stripped(self):
        sql = "SELECT * /* comment */ FROM cached_production_orders"
        result = validate_sql(sql)
        assert "/*" not in result

    # === Edge cases ===

    def test_empty_query_raises(self):
        with pytest.raises(ChatSQLError, match="空"):
            validate_sql("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ChatSQLError, match="空"):
            validate_sql("   ")

    def test_non_select_query_raises(self):
        with pytest.raises(ChatSQLError, match="SELECT"):
            validate_sql("SHOW TABLES")

    def test_multi_statement_blocked(self):
        with pytest.raises(ChatSQLError, match="多条"):
            validate_sql("SELECT 1; SELECT 2")

    def test_unknown_table_blocked(self):
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql("SELECT * FROM users")

    def test_max_length_enforced(self):
        long_query = "SELECT * FROM cached_production_orders WHERE " + "x = 1 AND " * 300
        with pytest.raises(ChatSQLError, match="过长"):
            validate_sql(long_query)

    def test_trailing_semicolon_stripped(self):
        result = validate_sql("SELECT * FROM cached_production_orders;")
        assert ";" not in result

    def test_sync_history_allowed(self):
        result = validate_sql("SELECT * FROM sync_history")
        assert "sync_history" in result
