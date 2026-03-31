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


class TestSqlparseTableExtraction:
    """Robustness tests for sqlparse-based table extraction."""

    # === CTE handling ===

    def test_cte_alias_not_treated_as_table(self):
        """CTE alias names should be excluded from whitelist check."""
        sql = (
            "WITH recent AS ("
            "SELECT * FROM cached_production_orders WHERE 1=1"
            ") SELECT * FROM recent"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_multiple_ctes(self):
        """Multiple comma-separated CTEs should all be recognized."""
        sql = (
            "WITH orders AS ("
            "  SELECT mto_number, bill_no FROM cached_production_orders"
            "), bom AS ("
            "  SELECT mo_bill_no, material_code FROM cached_production_bom"
            ") "
            "SELECT o.mto_number, b.material_code "
            "FROM orders o JOIN bom b ON o.bill_no = b.mo_bill_no"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_cte_with_real_table_inside_blocked(self):
        """A CTE referencing a non-whitelisted table should be blocked."""
        sql = (
            "WITH evil AS ("
            "  SELECT * FROM secret_passwords"
            ") SELECT * FROM evil"
        )
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql(sql)

    def test_recursive_cte(self):
        """WITH RECURSIVE should work and recognize the CTE name."""
        sql = (
            "WITH RECURSIVE tree AS ("
            "  SELECT bill_no, 1 AS depth FROM cached_production_orders "
            "  WHERE mto_number = 'AK2510034'"
            ") SELECT * FROM tree"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    # === Subqueries ===

    def test_subquery_in_from(self):
        """Subquery in FROM clause should have its tables checked."""
        sql = (
            "SELECT sub.mto_number FROM "
            "(SELECT mto_number FROM cached_production_orders) sub"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_subquery_in_where(self):
        """Subquery in WHERE clause should have its tables checked."""
        sql = (
            "SELECT * FROM cached_production_orders "
            "WHERE mto_number IN ("
            "  SELECT mto_number FROM cached_sales_orders"
            ")"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_subquery_with_forbidden_table_blocked(self):
        """Subquery referencing non-whitelisted table should be blocked."""
        sql = (
            "SELECT * FROM cached_production_orders "
            "WHERE bill_no IN (SELECT bill_no FROM evil_table)"
        )
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql(sql)

    def test_nested_subquery(self):
        """Deeply nested subqueries should still be validated."""
        sql = (
            "SELECT * FROM cached_production_orders "
            "WHERE mto_number IN ("
            "  SELECT mto_number FROM cached_sales_orders "
            "  WHERE order_id IN ("
            "    SELECT order_id FROM cached_sales_delivery"
            "  )"
            ")"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_nested_subquery_with_forbidden_table(self):
        """Deeply nested forbidden table should still be caught."""
        sql = (
            "SELECT * FROM cached_production_orders "
            "WHERE mto_number IN ("
            "  SELECT mto_number FROM cached_sales_orders "
            "  WHERE order_id IN ("
            "    SELECT order_id FROM users"
            "  )"
            ")"
        )
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql(sql)

    # === JOINs ===

    def test_multiple_joins(self):
        """Multiple JOINs across whitelisted tables should pass."""
        sql = (
            "SELECT a.mto_number, b.material_code, c.receipt_qty "
            "FROM cached_production_orders a "
            "JOIN cached_production_bom b ON a.bill_no = b.mo_bill_no "
            "LEFT JOIN cached_production_receipts c ON b.material_code = c.material_code"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_join_with_forbidden_table(self):
        """JOIN on a non-whitelisted table should be blocked."""
        sql = (
            "SELECT a.* FROM cached_production_orders a "
            "JOIN secret_table b ON a.id = b.id"
        )
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql(sql)

    # === Complex combinations ===

    def test_cte_with_join_and_subquery(self):
        """Complex query combining CTE, JOIN, and subquery."""
        sql = (
            "WITH active_mtos AS ("
            "  SELECT DISTINCT mto_number FROM cached_production_orders"
            ") "
            "SELECT a.mto_number, b.material_code "
            "FROM active_mtos a "
            "JOIN cached_production_bom b ON a.mto_number = b.mto_number "
            "WHERE b.material_code IN ("
            "  SELECT material_code FROM cached_purchase_orders"
            ")"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_comma_separated_tables_in_from(self):
        """FROM t1, t2 style should detect both tables."""
        sql = (
            "SELECT a.mto_number, b.bill_no "
            "FROM cached_production_orders a, cached_production_bom b "
            "WHERE a.bill_no = b.mo_bill_no"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_comma_separated_with_forbidden_table(self):
        """FROM t1, evil_table should be caught."""
        sql = (
            "SELECT * FROM cached_production_orders a, evil_table b "
            "WHERE a.id = b.id"
        )
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql(sql)

    # === Edge cases ===

    def test_table_name_as_string_literal_not_flagged(self):
        """Table names appearing only in string literals should not be flagged.

        Note: after comment stripping and sqlparse parsing, string literals
        are not treated as table references.
        """
        sql = (
            "SELECT * FROM cached_production_orders "
            "WHERE note = 'from evil_table'"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_aggregate_with_group_by(self):
        """Aggregate query with GROUP BY should work."""
        sql = (
            "SELECT mto_number, COUNT(*) as cnt, SUM(qty) as total "
            "FROM cached_production_orders "
            "GROUP BY mto_number "
            "HAVING COUNT(*) > 1 "
            "ORDER BY total DESC"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_union_of_whitelisted_tables(self):
        """UNION across whitelisted tables should pass."""
        sql = (
            "SELECT mto_number, 'order' as source FROM cached_production_orders "
            "UNION ALL "
            "SELECT mto_number, 'receipt' as source FROM cached_production_receipts"
        )
        result = validate_sql(sql)
        assert "LIMIT 100" in result

    def test_union_with_forbidden_table(self):
        """UNION referencing a forbidden table should be blocked."""
        sql = (
            "SELECT mto_number FROM cached_production_orders "
            "UNION ALL "
            "SELECT mto_number FROM evil_table"
        )
        with pytest.raises(ChatSQLError, match="不允许访问表"):
            validate_sql(sql)
