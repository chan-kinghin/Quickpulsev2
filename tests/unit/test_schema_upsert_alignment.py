"""Architectural invariant: UNIQUE constraints in schema.sql must match
ON CONFLICT clauses in sync_service.py.

bug-patterns.md #5 has now recurred 3 times (commits bcedaee, BUGFIX_PLAN
Issue 2, Bug 7 / 2026-04-26). Every recurrence has been the same shape:
the table-level UNIQUE constraint omits a column that the upsert's
ON CONFLICT clause assumes is part of the conflict key, causing silent
row migration when two logical entities share the constraint key.

This test parses both files and asserts the column sets are byte-equal
for each table referenced. Run on every PR — catches Pattern 5 regressions
before they ship.
"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "src" / "database" / "schema.sql"
SYNC = REPO_ROOT / "src" / "sync" / "sync_service.py"

# Maps each ON CONFLICT clause's table to its constraint columns. Every
# table written by sync_service must appear here when this test discovers
# it; the assertion below cross-checks against schema.sql.
TABLE_FROM_INSERT = re.compile(
    r"INSERT\s+INTO\s+\{?(\w+)\}?", re.IGNORECASE
)
ON_CONFLICT = re.compile(
    r"ON\s+CONFLICT\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE
)
CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)^\);",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
UNIQUE_CLAUSE = re.compile(
    r"^\s*UNIQUE\s*\(\s*([^)]+?)\s*\)",
    re.IGNORECASE | re.MULTILINE,
)

# Some sync upserts write to a TABLE_FOO constant. Resolve those.
CONSTANT_DEFS = re.compile(r"^\s*TABLE_\w+\s*=\s*[\"']([\w]+)[\"']", re.MULTILINE)


def _normalize_columns(raw: str) -> tuple[str, ...]:
    """Lowercase, strip, sort the column list for set-equality compare."""
    return tuple(sorted(c.strip().lower() for c in raw.split(",") if c.strip()))


def _resolve_constants(sync_text: str) -> dict[str, str]:
    """Map module-level TABLE_* constants to their string values."""
    return {
        f"TABLE_{m.group(0).split('=')[0].split('TABLE_')[1].strip()}"
        if False else
        m.group(0).split("=")[0].strip(): m.group(1)
        for m in CONSTANT_DEFS.finditer(sync_text)
    }


def _parse_schema_uniques() -> dict[str, set[tuple[str, ...]]]:
    """For each table in schema.sql, collect every table-level UNIQUE clause.
    A table can have multiple UNIQUEs (rare, but allowed); we keep the set."""
    text = SCHEMA.read_text(encoding="utf-8")
    out: dict[str, set[tuple[str, ...]]] = {}
    for m in CREATE_TABLE.finditer(text):
        table = m.group(1).lower()
        body = m.group(2)
        for u in UNIQUE_CLAUSE.finditer(body):
            cols = _normalize_columns(u.group(1))
            out.setdefault(table, set()).add(cols)
    return out


def _parse_sync_upserts() -> list[tuple[str, tuple[str, ...], int]]:
    """Pair each INSERT INTO <table> with the next ON CONFLICT clause in the
    same statement. Returns (table_name, conflict_cols, line_no) tuples."""
    text = SYNC.read_text(encoding="utf-8")
    constants = _resolve_constants(text)
    pairs: list[tuple[str, tuple[str, ...], int]] = []
    # Walk INSERT...ON CONFLICT pairs in document order.
    insert_iter = list(TABLE_FROM_INSERT.finditer(text))
    conflict_iter = list(ON_CONFLICT.finditer(text))
    if len(insert_iter) != len(conflict_iter):
        # Not strictly required, but our sync layer happens to maintain 1:1.
        # If this ever drifts, the test should still find each pair via offset
        # matching rather than zip.
        pass
    for ins in insert_iter:
        table_token = ins.group(1)
        # If the token is a TABLE_* constant, resolve to its string value.
        table = constants.get(table_token, table_token).lower()
        # Find the first ON CONFLICT after this INSERT.
        next_conflict = next(
            (c for c in conflict_iter if c.start() > ins.start()), None
        )
        if next_conflict is None:
            continue
        cols = _normalize_columns(next_conflict.group(1))
        line_no = text.count("\n", 0, next_conflict.start()) + 1
        pairs.append((table, cols, line_no))
    return pairs


def test_every_on_conflict_matches_a_schema_unique():
    """Pattern 5 regression guard: every ON CONFLICT key set must exist as
    a UNIQUE on the same table in schema.sql.

    If this test fails, the upsert's conflict key is wider or narrower than
    what the schema enforces. SQLite will either raise (no matching unique)
    or silently migrate rows (omitted column in UNIQUE).
    """
    schema = _parse_schema_uniques()
    upserts = _parse_sync_upserts()

    assert upserts, "No INSERT...ON CONFLICT pairs found in sync_service.py"

    misaligned: list[str] = []
    for table, cols, line in upserts:
        table_uniques = schema.get(table)
        if not table_uniques:
            misaligned.append(
                f"sync_service.py:{line} writes table `{table}` with ON CONFLICT"
                f"({', '.join(cols)}), but schema.sql has no table-level UNIQUE on `{table}`."
            )
            continue
        if cols not in table_uniques:
            schema_keys = " | ".join(
                "(" + ", ".join(u) + ")" for u in sorted(table_uniques)
            )
            misaligned.append(
                f"sync_service.py:{line} ON CONFLICT({', '.join(cols)}) on `{table}` "
                f"does not match any UNIQUE in schema.sql. Schema UNIQUEs: {schema_keys}"
            )

    if misaligned:
        report = "\n  - ".join([""] + misaligned)
        raise AssertionError(
            f"Schema/upsert alignment violations ({len(misaligned)}):{report}\n\n"
            "bug-patterns.md #5: every ON CONFLICT key set MUST equal a UNIQUE "
            "on the same table. Two recurrences shipped to prod via this exact "
            "drift; this test exists to make the third one impossible."
        )


def test_subcontract_orders_unique_includes_mto_number():
    """Bug 7 / 2026-04-26 regression guard. Explicit name for the most
    recent recurrence — easy to grep when the next aux-keyed table comes
    up for review."""
    schema = _parse_schema_uniques()
    sub = schema.get("cached_subcontracting_orders")
    assert sub, "cached_subcontracting_orders missing from schema.sql"
    has_mto_in_unique = any("mto_number" in u for u in sub)
    assert has_mto_in_unique, (
        "cached_subcontracting_orders UNIQUE must include mto_number. "
        "Without it, the upsert silently migrates rows between MTOs of the "
        "same customer that share a supplier subcontract bill_no — produces "
        "the ghost-row pattern from Bug 7 (DS256203S / 07.25.80)."
    )
