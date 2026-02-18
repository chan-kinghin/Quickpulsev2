#!/usr/bin/env python3
"""Benchmark harness — compares the simple chat pipeline vs. the agent pipeline.

Sends identical questions to both pipelines, captures timing, token usage,
SQL generated, and full response text. Outputs a comparison table to stdout
and detailed JSON results to scripts/benchmark_results.json.

Usage:
    # Full benchmark (requires DEEPSEEK_* env vars and SQLite DB)
    python scripts/benchmark_chat_pipelines.py

    # Dry-run: validate setup without making LLM calls
    python scripts/benchmark_chat_pipelines.py --dry-run

    # Run a subset of questions
    python scripts/benchmark_chat_pipelines.py --questions 0 2 5
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.config import DeepSeekConfig
from src.database.connection import Database
from src.chat.client import DeepSeekClient
from src.chat.prompts import SYSTEM_PROMPT_ANALYTICS, SYSTEM_PROMPT_SUMMARY
from src.chat.context import build_sql_result_context
from src.chat.sql_guard import validate_sql
from src.agents.base import AgentLLMClient, AgentStep
from src.agents.chat.orchestrator import AgentChatOrchestrator
from src.agents.tools.sql_query import create_sql_query_tool
from src.agents.tools.schema_lookup import create_schema_lookup_tool
from src.agents.tools.mto_lookup import create_mto_lookup_tool
from src.agents.tools.config_lookup import create_config_lookup_tool
from src.mto_config import MTOConfig
from src.exceptions import ChatSQLError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Benchmark questions
# ---------------------------------------------------------------------------

BENCHMARK_QUESTIONS: List[Dict[str, str]] = [
    {
        "id": "q1_mto_lookup",
        "category": "MTO lookup",
        "question": "AK2510034的入库完成率是多少",
    },
    {
        "id": "q2_schema",
        "category": "Schema",
        "question": "cached_production_bom表有哪些字段，各自是什么含义",
    },
    {
        "id": "q3_domain_concept",
        "category": "Domain concept",
        "question": "什么是超领，怎么通过数据检测超领情况",
    },
    {
        "id": "q4_analytical",
        "category": "Analytical",
        "question": "哪些物料的入库完成率最低，请列出前10个",
    },
    {
        "id": "q5_ambiguous",
        "category": "Ambiguous",
        "question": "帮我看看最近的订单情况",
    },
    {
        "id": "q6_aggregation",
        "category": "Aggregation",
        "question": "统计各物料类型的平均入库完成率",
    },
    {
        "id": "q7_error_prone",
        "category": "Error-prone SQL",
        "question": "查询所有入库数量超过需求数量的记录",
    },
    {
        "id": "q8_multi_table",
        "category": "Multi-table",
        "question": "对比采购入库和生产入库的总完成数量",
    },
]


# ---------------------------------------------------------------------------
# Data models for results
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Captured result from a single pipeline run."""

    pipeline: str  # "simple" or "agent"
    question_id: str
    question: str
    wall_clock_ms: float = 0.0
    llm_call_count: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    response_text: str = ""
    sql_generated: Optional[str] = None
    sql_result_rows: int = 0
    error: Optional[str] = None
    self_corrections: int = 0
    agent_steps: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Token-counting wrapper for DeepSeekClient (simple pipeline)
# ---------------------------------------------------------------------------

class InstrumentedDeepSeekClient:
    """Wraps DeepSeekClient to count LLM calls and approximate tokens."""

    def __init__(self, config: DeepSeekConfig):
        self._client = DeepSeekClient(config)
        self._config = config
        # We also keep a raw AsyncOpenAI for non-streaming usage counting
        from openai import AsyncOpenAI
        self._raw_client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=float(config.timeout_seconds),
        )
        self.call_count = 0
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0

    async def chat(self, messages: List[Dict[str, str]], system_prompt: str) -> str:
        """Non-streaming chat with token counting via the raw client."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        response = await self._raw_client.chat.completions.create(
            model=self._config.model,
            messages=full_messages,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
            stream=False,
        )
        self.call_count += 1
        if response.usage:
            self.total_tokens += response.usage.total_tokens
            self.input_tokens += response.usage.prompt_tokens
            self.output_tokens += response.usage.completion_tokens
        return response.choices[0].message.content or ""

    async def stream_chat_collect(
        self, messages: List[Dict[str, str]], system_prompt: str
    ) -> str:
        """Streaming chat, collected into a single string. Uses raw client
        for token counting via a non-streaming call."""
        # Use non-streaming to get accurate token counts
        return await self.chat(messages, system_prompt)

    def reset(self):
        self.call_count = 0
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0

    async def close(self):
        await self._client.close()
        await self._raw_client.close()


# ---------------------------------------------------------------------------
# Token-counting wrapper for AgentLLMClient (agent pipeline)
# ---------------------------------------------------------------------------

class InstrumentedAgentLLMClient(AgentLLMClient):
    """Extends AgentLLMClient with call counting."""

    def __init__(self, config: DeepSeekConfig):
        super().__init__(config)
        self.call_count = 0
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0

    async def chat_with_tools(self, messages, tools, temperature=None):
        result = await super().chat_with_tools(messages, tools, temperature)
        self.call_count += 1
        usage = result.get("usage", {})
        self.total_tokens += usage.get("total_tokens", 0)
        self.input_tokens += usage.get("prompt_tokens", 0)
        self.output_tokens += usage.get("completion_tokens", 0)
        return result

    def reset(self):
        self.call_count = 0
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0


# ---------------------------------------------------------------------------
# Simple pipeline runner
# ---------------------------------------------------------------------------

async def run_simple_pipeline(
    client: InstrumentedDeepSeekClient,
    db: Database,
    question: str,
    question_id: str,
) -> PipelineResult:
    """Replicate the _analytics_stream flow from src/api/routers/chat.py."""
    client.reset()
    result = PipelineResult(
        pipeline="simple",
        question_id=question_id,
        question=question,
    )

    messages = [{"role": "user", "content": question}]
    system_prompt = SYSTEM_PROMPT_ANALYTICS

    t0 = time.perf_counter()
    try:
        # Step 1: LLM generates SQL
        sql_response = await client.chat(messages, system_prompt)

        # Extract SQL from fenced block
        m = re.search(r"```sql\s*(.*?)\s*```", sql_response, re.DOTALL | re.IGNORECASE)
        raw_sql = m.group(1).strip() if m else None

        if not raw_sql:
            # LLM didn't return SQL — the response itself is the answer
            result.response_text = sql_response
            result.wall_clock_ms = (time.perf_counter() - t0) * 1000
            result.llm_call_count = client.call_count
            result.total_tokens = client.total_tokens
            result.input_tokens = client.input_tokens
            result.output_tokens = client.output_tokens
            return result

        # Step 2: Validate SQL
        try:
            safe_sql = validate_sql(raw_sql)
        except ChatSQLError as exc:
            result.error = f"SQL validation failed: {exc}"
            result.sql_generated = raw_sql
            result.wall_clock_ms = (time.perf_counter() - t0) * 1000
            result.llm_call_count = client.call_count
            result.total_tokens = client.total_tokens
            result.input_tokens = client.input_tokens
            result.output_tokens = client.output_tokens
            return result

        result.sql_generated = safe_sql

        # Step 3: Execute SQL
        try:
            rows, column_names = await db.execute_read_with_columns(safe_sql)
            result.sql_result_rows = len(rows)
        except Exception as exc:
            result.error = f"SQL execution failed: {exc}"
            result.wall_clock_ms = (time.perf_counter() - t0) * 1000
            result.llm_call_count = client.call_count
            result.total_tokens = client.total_tokens
            result.input_tokens = client.input_tokens
            result.output_tokens = client.output_tokens
            return result

        # Step 4: Summarize results
        result_context = build_sql_result_context(rows, column_names)
        summary_messages = messages + [
            {"role": "assistant", "content": f"```sql\n{safe_sql}\n```"},
            {"role": "user", "content": f"查询结果如下，请用中文简要总结：\n{result_context}"},
        ]

        summary = await client.stream_chat_collect(summary_messages, SYSTEM_PROMPT_SUMMARY)
        result.response_text = summary

    except Exception as exc:
        result.error = str(exc)
    finally:
        result.wall_clock_ms = (time.perf_counter() - t0) * 1000
        result.llm_call_count = client.call_count
        result.total_tokens = client.total_tokens
        result.input_tokens = client.input_tokens
        result.output_tokens = client.output_tokens

    return result


# ---------------------------------------------------------------------------
# Agent pipeline runner
# ---------------------------------------------------------------------------

async def run_agent_pipeline(
    llm_client: InstrumentedAgentLLMClient,
    db: Database,
    mto_config: MTOConfig,
    question: str,
    question_id: str,
    mto_handler=None,
) -> PipelineResult:
    """Replicate the AgentChatOrchestrator flow."""
    llm_client.reset()
    result = PipelineResult(
        pipeline="agent",
        question_id=question_id,
        question=question,
    )

    # Create tools
    schema_tool = create_schema_lookup_tool(db)
    config_tool = create_config_lookup_tool(mto_config)
    sql_tool = create_sql_query_tool(db)
    mto_tool = create_mto_lookup_tool(mto_handler)

    orchestrator = AgentChatOrchestrator(
        llm_client=llm_client,
        schema_tool=schema_tool,
        config_tool=config_tool,
        sql_tool=sql_tool,
        mto_tool=mto_tool,
    )

    # Collect events
    events: List[Dict[str, Any]] = []

    async def on_event(event: Dict[str, Any]):
        events.append(event)

    t0 = time.perf_counter()
    try:
        await orchestrator.run(question=question, on_event=on_event)
    except Exception as exc:
        result.error = str(exc)
    finally:
        result.wall_clock_ms = (time.perf_counter() - t0) * 1000
        result.llm_call_count = llm_client.call_count
        result.total_tokens = llm_client.total_tokens
        result.input_tokens = llm_client.input_tokens
        result.output_tokens = llm_client.output_tokens

    # Parse events
    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "token":
            result.response_text += ev.get("content", "")
        elif ev_type == "sql":
            result.sql_generated = ev.get("query", "")
        elif ev_type == "error":
            if not result.error:
                result.error = ev.get("message", "")
        elif ev_type == "agent_step":
            step_info = {
                "agent": ev.get("agent"),
                "step_number": ev.get("step_number"),
                "tool_name": ev.get("tool_name"),
                "tool_args": ev.get("tool_args"),
            }
            result.agent_steps.append(step_info)
            # Count SQL retry steps as self-corrections
            if (
                ev.get("tool_name") == "sql_query"
                and ev.get("agent") == "reasoning"
                and ev.get("step_number", 0) > 1
            ):
                result.self_corrections += 1

    return result


# ---------------------------------------------------------------------------
# Dry-run mode: validate setup
# ---------------------------------------------------------------------------

async def dry_run(db_path: Path, config: DeepSeekConfig):
    """Validate that all components can be initialized without LLM calls."""
    print("=" * 60)
    print("DRY RUN — validating setup")
    print("=" * 60)

    # Check DeepSeek config
    print(f"\nDeepSeek API key: {'configured' if config.is_available() else 'MISSING'}")
    print(f"  Model: {config.model}")
    print(f"  Base URL: {config.base_url}")
    print(f"  Max tokens: {config.max_tokens}")

    # Check database
    print(f"\nDatabase path: {db_path}")
    if db_path.exists():
        db = Database(db_path)
        await db.connect()
        rows = await db.execute_read("SELECT COUNT(*) FROM cached_production_orders")
        count = rows[0][0] if rows else 0
        print(f"  cached_production_orders: {count} rows")
        rows = await db.execute_read("SELECT COUNT(*) FROM cached_production_bom")
        count = rows[0][0] if rows else 0
        print(f"  cached_production_bom: {count} rows")
        await db.close()
    else:
        print("  WARNING: database file does not exist")

    # Check MTO config
    config_path = PROJECT_ROOT / "config" / "mto_config.json"
    print(f"\nMTO config: {config_path}")
    if config_path.exists():
        mto_config = MTOConfig(str(config_path))
        print(f"  Material classes: {len(mto_config.material_classes)}")
        for mc in mto_config.material_classes:
            print(f"    - {mc.id}: {mc.display_name} ({mc.pattern.pattern})")
        print(f"  Receipt sources: {list(mto_config.receipt_sources.keys())}")
    else:
        print("  WARNING: mto_config.json not found")

    # List questions
    print(f"\nBenchmark questions: {len(BENCHMARK_QUESTIONS)}")
    for i, q in enumerate(BENCHMARK_QUESTIONS):
        print(f"  [{i}] {q['id']}: {q['question'][:50]}...")

    print("\n" + "=" * 60)
    print("Dry run complete. Use without --dry-run to execute benchmark.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Stub MTO handler for agent pipeline (when no real handler available)
# ---------------------------------------------------------------------------

class _SimpleParent:
    """Minimal parent item for benchmark MTO lookups."""
    def __init__(self, row):
        self.bill_no = row[0]
        self.material_code = row[1]
        self.material_name = row[2]
        self.qty = row[3]


class _SimpleChild:
    """Minimal child item for benchmark MTO lookups."""
    def __init__(self, row):
        self.material_code = row[0]
        self.material_name = row[1]
        self.metrics = None


class _SimpleMTOResult:
    """Minimal MTO result for benchmark."""
    def __init__(self, parent, children):
        self.parent = parent
        self.children = children


class DatabaseBackedMTOStub:
    """MTO handler that queries SQLite directly for benchmark testing."""

    def __init__(self, db: Database):
        self._db = db

    async def get_status(self, mto_number: str):
        """Query MTO status via direct SQL."""
        # Get parent (production order)
        parent_rows = await self._db.execute_read(
            "SELECT bill_no, material_code, material_name, qty "
            "FROM cached_production_orders WHERE mto_number = ? LIMIT 1",
            (mto_number,),
        )
        if not parent_rows:
            return None

        parent = _SimpleParent(parent_rows[0])

        # Get children (BOM items)
        child_rows = await self._db.execute_read(
            "SELECT material_code, material_name "
            "FROM cached_production_bom WHERE mto_number = ? LIMIT 20",
            (mto_number,),
        )
        children = [_SimpleChild(row) for row in child_rows]

        return _SimpleMTOResult(parent, children)


# ---------------------------------------------------------------------------
# Pretty-print comparison table
# ---------------------------------------------------------------------------

def print_comparison_table(results: List[PipelineResult]):
    """Print a side-by-side comparison table to stdout."""

    # Group by question
    by_question: Dict[str, Dict[str, PipelineResult]] = {}
    for r in results:
        by_question.setdefault(r.question_id, {})[r.pipeline] = r

    print("\n" + "=" * 100)
    print("BENCHMARK RESULTS — Simple Pipeline vs. Agent Pipeline")
    print("=" * 100)

    header = (
        f"{'Question':<20} {'Pipeline':<8} {'Time(ms)':>10} {'LLM Calls':>10} "
        f"{'Tokens':>8} {'In Tok':>8} {'Out Tok':>8} {'SQL Rows':>9} {'Error':>6}"
    )
    print(header)
    print("-" * 100)

    for qid in [q["id"] for q in BENCHMARK_QUESTIONS]:
        entries = by_question.get(qid, {})
        for pipeline_name in ["simple", "agent"]:
            r = entries.get(pipeline_name)
            if r:
                err = "YES" if r.error else "no"
                print(
                    f"{qid:<20} {pipeline_name:<8} {r.wall_clock_ms:>10.0f} "
                    f"{r.llm_call_count:>10} {r.total_tokens:>8} "
                    f"{r.input_tokens:>8} {r.output_tokens:>8} "
                    f"{r.sql_result_rows:>9} {err:>6}"
                )
        print("-" * 100)

    # Aggregated stats
    simple_results = [r for r in results if r.pipeline == "simple"]
    agent_results = [r for r in results if r.pipeline == "agent"]

    if simple_results and agent_results:
        print("\nAGGREGATED STATS")
        print("-" * 60)

        def agg(items: List[PipelineResult]):
            return {
                "avg_time_ms": sum(r.wall_clock_ms for r in items) / len(items),
                "total_tokens": sum(r.total_tokens for r in items),
                "avg_tokens": sum(r.total_tokens for r in items) / len(items),
                "total_calls": sum(r.llm_call_count for r in items),
                "avg_calls": sum(r.llm_call_count for r in items) / len(items),
                "errors": sum(1 for r in items if r.error),
                "self_corrections": sum(r.self_corrections for r in items),
            }

        s = agg(simple_results)
        a = agg(agent_results)

        row_fmt = "{:<25} {:>15} {:>15}"
        print(row_fmt.format("Metric", "Simple", "Agent"))
        print("-" * 60)
        print(row_fmt.format("Avg time (ms)", f"{s['avg_time_ms']:.0f}", f"{a['avg_time_ms']:.0f}"))
        print(row_fmt.format("Avg LLM calls", f"{s['avg_calls']:.1f}", f"{a['avg_calls']:.1f}"))
        print(row_fmt.format("Avg tokens/question", f"{s['avg_tokens']:.0f}", f"{a['avg_tokens']:.0f}"))
        print(row_fmt.format("Total tokens", f"{s['total_tokens']}", f"{a['total_tokens']}"))
        print(row_fmt.format("Errors", f"{s['errors']}", f"{a['errors']}"))
        print(row_fmt.format("Self-corrections", f"{s['self_corrections']}", f"{a['self_corrections']}"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Benchmark simple vs. agent chat pipelines")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without LLM calls")
    parser.add_argument(
        "--questions",
        nargs="*",
        type=int,
        help="Indices of questions to run (default: all)",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "scripts" / "benchmark_results.json"),
        help="Path for JSON results output",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    ds_config = DeepSeekConfig()
    db_path = PROJECT_ROOT / "data" / "quickpulse.db"

    if args.dry_run:
        await dry_run(db_path, ds_config)
        return

    if not ds_config.is_available():
        print("ERROR: DEEPSEEK_API_KEY not set. Set DEEPSEEK_* env vars or add to .env")
        sys.exit(1)

    # Select questions
    questions = BENCHMARK_QUESTIONS
    if args.questions is not None:
        questions = [BENCHMARK_QUESTIONS[i] for i in args.questions if i < len(BENCHMARK_QUESTIONS)]
        if not questions:
            print("ERROR: No valid question indices provided")
            sys.exit(1)

    # Initialize shared resources
    db = Database(db_path)
    if db_path.exists():
        await db.connect()
        logger.info("Database connected: %s", db_path)
    else:
        logger.warning("Database not found at %s — SQL queries will fail gracefully", db_path)
        await db.connect()

    mto_config_path = PROJECT_ROOT / "config" / "mto_config.json"
    mto_config = MTOConfig(str(mto_config_path))

    # Create clients — agent pipeline uses AGENT_* config with DEEPSEEK_* fallback
    from src.config import AgentLLMConfig
    agent_llm_config = AgentLLMConfig().resolve()

    simple_client = InstrumentedDeepSeekClient(ds_config)
    agent_client = InstrumentedAgentLLMClient(agent_llm_config)

    print(f"Simple pipeline model: {ds_config.model} ({ds_config.base_url})")
    print(f"Agent pipeline model:  {agent_llm_config.model} ({agent_llm_config.base_url})")

    # Database-backed MTO handler for agent pipeline
    mto_handler = DatabaseBackedMTOStub(db)

    all_results: List[PipelineResult] = []

    print(f"\nRunning benchmark with {len(questions)} questions...")
    print(f"Model: {ds_config.model}")
    print(f"Database: {db_path} (exists={db_path.exists()})")
    print()

    for i, q in enumerate(questions):
        qid = q["id"]
        question_text = q["question"]
        print(f"[{i + 1}/{len(questions)}] {qid}: {question_text}")

        # Run simple pipeline
        print(f"  Running simple pipeline...", end="", flush=True)
        simple_result = await run_simple_pipeline(
            simple_client, db, question_text, qid
        )
        all_results.append(simple_result)
        err_tag = f" [ERROR: {simple_result.error[:40]}]" if simple_result.error else ""
        print(
            f" {simple_result.wall_clock_ms:.0f}ms, "
            f"{simple_result.llm_call_count} calls, "
            f"{simple_result.total_tokens} tokens{err_tag}"
        )

        # Run agent pipeline
        print(f"  Running agent pipeline...", end="", flush=True)
        agent_result = await run_agent_pipeline(
            agent_client, db, mto_config, question_text, qid, mto_handler
        )
        all_results.append(agent_result)
        err_tag = f" [ERROR: {agent_result.error[:40]}]" if agent_result.error else ""
        steps_info = f", {len(agent_result.agent_steps)} steps"
        corrections = f", {agent_result.self_corrections} corrections" if agent_result.self_corrections else ""
        print(
            f" {agent_result.wall_clock_ms:.0f}ms, "
            f"{agent_result.llm_call_count} calls, "
            f"{agent_result.total_tokens} tokens{steps_info}{corrections}{err_tag}"
        )

        # Small delay between questions to avoid rate limits
        if i < len(questions) - 1:
            await asyncio.sleep(1.0)

    # Print comparison table
    print_comparison_table(all_results)

    # Save detailed JSON results
    output_path = Path(args.output)
    json_results = {
        "metadata": {
            "model": ds_config.model,
            "base_url": ds_config.base_url,
            "max_tokens": ds_config.max_tokens,
            "temperature": ds_config.temperature,
            "database": str(db_path),
            "database_exists": db_path.exists(),
            "question_count": len(questions),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "questions": [
            {"id": q["id"], "category": q["category"], "question": q["question"]}
            for q in questions
        ],
        "results": [asdict(r) for r in all_results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)

    print(f"\nDetailed results saved to: {output_path}")

    # Cleanup
    await simple_client.close()
    await agent_client.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
