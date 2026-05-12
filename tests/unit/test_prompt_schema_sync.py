"""Tests that agent prompts stay in sync with the database schema.

Prevents the recurring bug where tables are added to schema.sql but
forgotten in agent prompts, causing the LLM to reference non-existent
tables or miss available ones.

See: commits ff1bc66, 3bec57e for historical examples.
"""

import re
from pathlib import Path

import pytest

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "src" / "database" / "schema.sql"
PROMPTS_PATH = PROJECT_ROOT / "src" / "agents" / "chat" / "prompts.py"

# Tables that are internal infrastructure, not user-queryable data
INTERNAL_TABLES = {"sync_history"}

# Regex to extract CREATE TABLE names from schema.sql
TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.IGNORECASE)

# Regex to extract column definitions from CREATE TABLE blocks
COLUMN_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\);",
    re.DOTALL | re.IGNORECASE,
)


def _parse_schema_tables() -> set[str]:
    """Extract all table names from schema.sql."""
    sql = SCHEMA_PATH.read_text()
    return {m.group(1) for m in TABLE_RE.finditer(sql)} - INTERNAL_TABLES


def _parse_schema_columns(table_name: str) -> set[str]:
    """Extract user-facing column names for a table from schema.sql."""
    sql = SCHEMA_PATH.read_text()
    for m in COLUMN_RE.finditer(sql):
        if m.group(1) == table_name:
            body = m.group(2)
            cols = set()
            for line in body.split("\n"):
                line = line.strip().rstrip(",")
                if not line or line.startswith("--") or line.startswith("UNIQUE"):
                    continue
                # First word is the column name
                col = line.split()[0]
                if col.upper() in ("PRIMARY", "UNIQUE", "CHECK", "FOREIGN"):
                    continue
                cols.add(col)
            # Remove auto-managed columns that aren't useful for agent queries
            cols -= {"id", "raw_data", "synced_at"}
            return cols
    return set()


def _load_prompts() -> str:
    """Load the full prompts.py source text."""
    return PROMPTS_PATH.read_text()


class TestPromptSchemaSync:
    """Ensure agent prompts reference all queryable tables."""

    def test_all_schema_tables_in_retrieval_prompt(self):
        """Every data table in schema.sql must appear in RETRIEVAL_AGENT_PROMPT."""
        schema_tables = _parse_schema_tables()
        prompts_src = _load_prompts()

        # Extract RETRIEVAL_AGENT_PROMPT string content
        retrieval_match = re.search(
            r'RETRIEVAL_AGENT_PROMPT\s*=\s*"""\\\n(.*?)"""',
            prompts_src,
            re.DOTALL,
        )
        assert retrieval_match, "Could not find RETRIEVAL_AGENT_PROMPT in prompts.py"
        retrieval_text = retrieval_match.group(1)

        missing = {t for t in schema_tables if t not in retrieval_text}
        assert not missing, (
            f"Tables in schema.sql but missing from RETRIEVAL_AGENT_PROMPT: {missing}. "
            f"Add them to the '已知数据库结构' or '表用途语义映射' section."
        )

    def test_all_schema_tables_in_reasoning_prompt(self):
        """Every data table in schema.sql must appear in REASONING_AGENT_PROMPT."""
        schema_tables = _parse_schema_tables()
        prompts_src = _load_prompts()

        reasoning_match = re.search(
            r'REASONING_AGENT_PROMPT\s*=\s*"""\\\n(.*?)"""',
            prompts_src,
            re.DOTALL,
        )
        assert reasoning_match, "Could not find REASONING_AGENT_PROMPT in prompts.py"
        reasoning_text = reasoning_match.group(1)

        missing = {t for t in schema_tables if t not in reasoning_text}
        assert not missing, (
            f"Tables in schema.sql but missing from REASONING_AGENT_PROMPT: {missing}. "
            f"Add them to the '数据库表结构' section."
        )

    def test_no_phantom_tables_in_prompts(self):
        """Prompts must not reference tables that don't exist in schema.sql."""
        schema_tables = _parse_schema_tables() | INTERNAL_TABLES
        prompts_src = _load_prompts()

        # Find all cached_* table references in prompts
        prompt_tables = set(re.findall(r"cached_\w+", prompts_src))

        phantom = prompt_tables - schema_tables
        assert not phantom, (
            f"Tables referenced in prompts but not in schema.sql: {phantom}. "
            f"These will cause agent SQL failures."
        )

    def test_key_columns_mentioned_in_reasoning_prompt(self):
        """Reasoning prompt must mention key queryable columns for each table."""
        prompts_src = _load_prompts()

        reasoning_match = re.search(
            r'REASONING_AGENT_PROMPT\s*=\s*"""\\\n(.*?)"""',
            prompts_src,
            re.DOTALL,
        )
        assert reasoning_match
        reasoning_text = reasoning_match.group(1)

        schema_tables = _parse_schema_tables()
        missing_cols = {}

        for table in schema_tables:
            schema_cols = _parse_schema_columns(table)
            if not schema_cols:
                continue

            # Check that the table's section in the prompt mentions its columns
            # We only check critical columns (quantity fields and join keys)
            critical_cols = {
                c
                for c in schema_cols
                if any(
                    kw in c
                    for kw in (
                        "qty",
                        "mto_number",
                        "material_code",
                        "bill_no",
                        "bill_type",
                    )
                )
            }

            not_mentioned = {c for c in critical_cols if c not in reasoning_text}
            if not_mentioned:
                missing_cols[table] = not_mentioned

        assert not missing_cols, (
            f"Critical columns in schema.sql but not mentioned in REASONING_AGENT_PROMPT: "
            f"{missing_cols}. The agent won't know these columns exist."
        )

    def test_semantic_mapping_covers_all_receipt_tables(self):
        """The semantic mapping section must cover all receipt/delivery tables."""
        prompts_src = _load_prompts()

        # Tables that represent transaction data (receipts, deliveries, picking)
        transaction_tables = {
            "cached_production_receipts",
            "cached_purchase_receipts",
            "cached_material_picking",
            "cached_sales_delivery",
        }

        # Check in the semantic mapping section of REASONING_AGENT_PROMPT
        reasoning_match = re.search(
            r'REASONING_AGENT_PROMPT\s*=\s*"""\\\n(.*?)"""',
            prompts_src,
            re.DOTALL,
        )
        assert reasoning_match
        reasoning_text = reasoning_match.group(1)

        # Look for the semantic mapping section
        semantic_section = re.search(
            r"表用途语义映射.*?(?=\n##|\Z)", reasoning_text, re.DOTALL
        )
        assert semantic_section, (
            "REASONING_AGENT_PROMPT is missing '表用途语义映射' section. "
            "This section prevents wrong-table selection bugs."
        )

        semantic_text = semantic_section.group(0)
        missing = {t for t in transaction_tables if t not in semantic_text}
        assert not missing, (
            f"Transaction tables missing from semantic mapping: {missing}. "
            f"Without mapping, agent may confuse these tables."
        )


# --- FStatus enum guards (Pattern 9, 2026-05-12) ---

def test_status_enum_documented_in_retrieval_agent_prompt():
    """RETRIEVAL_AGENT_PROMPT must list all 6 FStatus codes so the LLM
    doesn't hallucinate filter values like '已审核' or 'in_production'."""
    from src.agents.chat.prompts import RETRIEVAL_AGENT_PROMPT
    for code in ["'1'", "'2'", "'3'", "'4'", "'5'", "'6'"]:
        assert code in RETRIEVAL_AGENT_PROMPT, (
            f"FStatus code {code} missing from RETRIEVAL_AGENT_PROMPT — "
            f"LLM will guess and hallucinate (see bug-patterns.md Pattern 9 "
            f"2026-05-12 occurrence)."
        )


def test_status_enum_documented_in_reasoning_agent_prompt():
    """REASONING_AGENT_PROMPT (the one that actually writes SQL) must
    list all 6 FStatus codes."""
    from src.agents.chat.prompts import REASONING_AGENT_PROMPT
    for code in ["'1'", "'2'", "'3'", "'4'", "'5'", "'6'"]:
        assert code in REASONING_AGENT_PROMPT, (
            f"FStatus code {code} missing from REASONING_AGENT_PROMPT."
        )


def test_business_phrase_in_production_maps_to_status_4():
    """The reasoning prompt must associate the user phrase '在生产'
    with the canonical status value '4' so it doesn't get translated
    to a hallucinated label like 'in_production'."""
    from src.agents.chat.prompts import REASONING_AGENT_PROMPT
    # Look for '在生产' within 200 chars of "'4'"
    idx_phrase = REASONING_AGENT_PROMPT.find("在生产")
    idx_code = REASONING_AGENT_PROMPT.find("'4'")
    assert idx_phrase != -1, "'在生产' missing from REASONING_AGENT_PROMPT"
    assert idx_code != -1, "'4' missing from REASONING_AGENT_PROMPT"
    assert abs(idx_phrase - idx_code) < 400, (
        "'在生产' and '4' must appear close enough in REASONING_AGENT_PROMPT "
        "for the LLM to associate them."
    )


def test_simple_chat_module_removed():
    """src/chat/ was deleted in 2026-05-12 — single chat path now goes
    through src/agents/. This test fails if the module is re-introduced."""
    import os
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    assert not os.path.exists(os.path.join(repo_root, "src", "chat")), (
        "src/chat/ should not exist — simple chat mode was retired. "
        "If you need to re-introduce it, update bug-patterns.md Pattern 9 "
        "with the new mitigation plan."
    )


def test_count_distinct_rule_for_entity_counts():
    """REASONING_AGENT_PROMPT must teach COUNT(DISTINCT entity_id) for
    questions like '有多少个计划跟踪号' — otherwise the agent uses COUNT(*)
    and counts row-level production-order lines (~1346) instead of distinct
    tracking numbers (~48). Verified live 2026-05-12 with the FStatus fix."""
    from src.agents.chat.prompts import REASONING_AGENT_PROMPT
    assert "COUNT(DISTINCT" in REASONING_AGENT_PROMPT, (
        "REASONING_AGENT_PROMPT must mention COUNT(DISTINCT ...) "
        "to guide entity-count questions away from COUNT(*)."
    )
    assert "mto_number" in REASONING_AGENT_PROMPT, (
        "REASONING_AGENT_PROMPT must show a concrete COUNT(DISTINCT mto_number) "
        "example — the canonical reproducer is '有多少个计划跟踪号'."
    )
    # The rule must reference the reproducer entity by Chinese name so the LLM
    # can match it to user wording.
    assert "计划跟踪号" in REASONING_AGENT_PROMPT
