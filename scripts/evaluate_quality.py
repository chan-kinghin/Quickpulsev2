#!/usr/bin/env python3
"""Quality evaluation framework for chat pipeline benchmark results.

Uses DeepSeek as an LLM-as-judge to blindly evaluate response quality
from the simple and agent chat pipelines.

Usage:
    python scripts/evaluate_quality.py
    python scripts/evaluate_quality.py --input scripts/benchmark_results.json
    python scripts/evaluate_quality.py --dry-run   # validate setup without API calls
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from openai import AsyncOpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIMENSIONS = [
    ("accuracy", "准确性", "回答是否正确？SQL是否有效？数据是否准确？"),
    ("completeness", "完整性", "是否覆盖了问题的所有方面？是否遗漏关键信息？"),
    ("helpfulness", "实用性", "回复是否有用、结构清晰、易于理解？"),
    ("error_handling", "错误处理", "是否优雅地处理了错误或边界情况？是否有自我纠正？"),
    ("transparency", "透明度", "是否展示了推理过程？用户能否理解系统是如何得出答案的？"),
]

DEFAULT_INPUT = "scripts/benchmark_results.json"
DEFAULT_OUTPUT = "scripts/evaluation_results.json"


# ---------------------------------------------------------------------------
# Evaluation prompt (Chinese, matching domain language)
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """\
你是一个专业的AI回复质量评估专家。你需要对两个AI助手针对同一问题的回复进行盲评。

## 评估维度（每项1-5分）

1. **准确性 (accuracy)**: 回答是否正确？生成的SQL是否有效？引用的数据是否准确？
   - 1分: 完全错误或答非所问
   - 3分: 部分正确，有明显错误
   - 5分: 完全正确，SQL有效，数据准确

2. **完整性 (completeness)**: 是否覆盖问题的所有方面？是否遗漏关键信息？
   - 1分: 严重遗漏，只回答了一小部分
   - 3分: 覆盖了主要方面，但遗漏了一些细节
   - 5分: 全面覆盖，没有遗漏

3. **实用性 (helpfulness)**: 回复是否有用、结构清晰、易于理解？
   - 1分: 难以理解，没有实际帮助
   - 3分: 基本有用，但组织不够清晰
   - 5分: 非常有用，结构清晰，重点突出

4. **错误处理 (error_handling)**: 面对异常或困难问题时是否优雅处理？是否有自我纠正？
   - 1分: 遇到问题就崩溃或给出错误结果
   - 3分: 能识别问题但处理方式一般
   - 5分: 优雅处理错误，有自我纠正能力

5. **透明度 (transparency)**: 是否展示推理过程？用户能否理解结果是如何得出的？
   - 1分: 黑箱回答，无任何解释
   - 3分: 有一些解释但不够详细
   - 5分: 清晰展示推理步骤和依据

## 评估规则

- 你会收到一个用户问题和两个回复（Response A 和 Response B）
- 请独立评估每个回复，不要因对比而偏向某一方
- 请严格按JSON格式返回评分结果
- 评分要有区分度，避免给所有维度都打相同分数
- 如果回复包含SQL，请评估SQL的正确性和效率

## 输出格式

请严格返回以下JSON格式（不要包含其他文本）：

```json
{
  "response_a": {
    "accuracy": <1-5>,
    "completeness": <1-5>,
    "helpfulness": <1-5>,
    "error_handling": <1-5>,
    "transparency": <1-5>,
    "brief_comment": "<一句话评价>"
  },
  "response_b": {
    "accuracy": <1-5>,
    "completeness": <1-5>,
    "helpfulness": <1-5>,
    "error_handling": <1-5>,
    "transparency": <1-5>,
    "brief_comment": "<一句话评价>"
  }
}
```
"""


def build_judge_user_prompt(question: str, response_a: str, response_b: str) -> str:
    """Build the user message for the judge LLM."""
    return f"""\
## 用户问题

{question}

## Response A

{response_a}

## Response B

{response_b}

请按照要求的JSON格式对两个回复进行评分。"""


# ---------------------------------------------------------------------------
# LLM Judge client
# ---------------------------------------------------------------------------

class LLMJudge:
    """Wraps AsyncOpenAI to call DeepSeek for evaluation."""

    def __init__(self) -> None:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY not set. Export it or add to .env file."
            )

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,
        )
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def evaluate(
        self, question: str, response_a: str, response_b: str
    ) -> Dict[str, Any]:
        """Ask the judge to score two responses. Returns parsed JSON dict."""
        user_prompt = build_judge_user_prompt(question, response_a, response_b)

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.1,  # low temperature for consistent scoring
            stream=False,
        )

        # Track token usage
        if response.usage:
            self.total_input_tokens += response.usage.prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens

        raw_text = response.choices[0].message.content or ""
        return self._parse_scores(raw_text)

    def _parse_scores(self, text: str) -> Dict[str, Any]:
        """Extract JSON scores from the judge's response."""
        # Try to find JSON in code block first
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            # Try to find bare JSON object
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end != -1:
                text = text[brace_start : brace_end + 1]

        try:
            scores = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse judge response as JSON: %s", text[:200])
            # Return neutral scores on parse failure
            neutral = {
                dim_key: 3
                for dim_key, _, _ in DIMENSIONS
            }
            neutral["brief_comment"] = "评分解析失败"
            return {"response_a": neutral.copy(), "response_b": neutral.copy()}

        # Validate structure
        for key in ("response_a", "response_b"):
            if key not in scores:
                scores[key] = {}
            for dim_key, _, _ in DIMENSIONS:
                val = scores[key].get(dim_key, 3)
                scores[key][dim_key] = max(1, min(5, int(val)))
            if "brief_comment" not in scores[key]:
                scores[key]["brief_comment"] = ""

        return scores

    async def close(self) -> None:
        await self._client.close()


# ---------------------------------------------------------------------------
# Result loading and normalization
# ---------------------------------------------------------------------------

def load_benchmark_results(path: str) -> Dict[str, Any]:
    """Load benchmark_results.json and validate its structure."""
    p = PROJECT_ROOT / path
    if not p.exists():
        raise FileNotFoundError(
            f"Benchmark results not found at {p}. "
            f"Run scripts/benchmark_chat_pipelines.py first."
        )

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Expect a "results" list (or top-level list)
    results = data.get("results") if isinstance(data, dict) else data
    if not results or not isinstance(results, list):
        raise ValueError(
            "benchmark_results.json must contain a 'results' list with per-question entries."
        )

    return data


def extract_response_text(pipeline_result: Dict[str, Any]) -> str:
    """Extract the full response text from a pipeline result.

    Handles various result structures:
    - {"response": "..."}
    - {"full_response": "..."}
    - {"sql": "...", "summary": "..."}
    - {"events": [...]} (agent mode)
    """
    if not pipeline_result:
        return "(无回复)"

    # Direct response text
    for key in ("response_text", "response", "full_response", "answer"):
        if key in pipeline_result and pipeline_result[key]:
            return str(pipeline_result[key])

    # SQL + summary composite
    parts = []
    if pipeline_result.get("sql"):
        parts.append(f"SQL查询:\n```sql\n{pipeline_result['sql']}\n```")
    if pipeline_result.get("summary"):
        parts.append(f"总结:\n{pipeline_result['summary']}")
    if parts:
        return "\n\n".join(parts)

    # Agent events
    events = pipeline_result.get("events", [])
    if events:
        text_parts = []
        for evt in events:
            if isinstance(evt, dict):
                if evt.get("type") == "token":
                    text_parts.append(evt.get("content", ""))
                elif evt.get("type") == "sql":
                    text_parts.append(f"\nSQL: {evt.get('query', '')}\n")
                elif evt.get("type") == "agent_step":
                    tool = evt.get("tool_name", "")
                    text_parts.append(f"\n[步骤: {tool}]\n")
        if text_parts:
            return "".join(text_parts)

    # Fallback: serialize the whole dict
    if pipeline_result.get("error"):
        return f"(错误: {pipeline_result['error']})"

    return "(无回复)"


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

async def evaluate_single_question(
    judge: LLMJudge,
    question: str,
    simple_response: str,
    agent_response: str,
    question_idx: int,
) -> Dict[str, Any]:
    """Evaluate a single question's responses with blind randomization."""

    # Randomize order to avoid position bias
    if random.random() < 0.5:
        a_is_simple = True
        resp_a = simple_response
        resp_b = agent_response
    else:
        a_is_simple = False
        resp_a = agent_response
        resp_b = simple_response

    logger.info(
        "Evaluating Q%d: A=%s, B=%s",
        question_idx + 1,
        "simple" if a_is_simple else "agent",
        "agent" if a_is_simple else "simple",
    )

    start = time.monotonic()
    scores = await judge.evaluate(question, resp_a, resp_b)
    elapsed_ms = (time.monotonic() - start) * 1000

    # Map back from A/B to simple/agent
    if a_is_simple:
        simple_scores = scores["response_a"]
        agent_scores = scores["response_b"]
    else:
        simple_scores = scores["response_b"]
        agent_scores = scores["response_a"]

    return {
        "question_index": question_idx,
        "question": question,
        "randomized_order": "simple=A" if a_is_simple else "simple=B",
        "simple_scores": simple_scores,
        "agent_scores": agent_scores,
        "judge_time_ms": round(elapsed_ms, 1),
    }


def _group_results_by_question(
    benchmark_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Group flat results list into per-question dicts with simple/agent keys.

    Handles two formats:
    1. Flat list with 'pipeline' field: [{pipeline: 'simple', ...}, {pipeline: 'agent', ...}]
    2. Pre-grouped: [{simple: {...}, agent: {...}, question: ...}]
    """
    results_list = benchmark_data.get("results", [])
    if not results_list:
        return []

    # Check if already grouped (has 'simple' or 'agent' key)
    if "simple" in results_list[0] or "agent" in results_list[0]:
        return results_list

    # Flat format: group by question_id
    from collections import OrderedDict
    grouped: Dict[str, Dict[str, Any]] = OrderedDict()
    for item in results_list:
        qid = item.get("question_id", item.get("question", "unknown"))
        if qid not in grouped:
            grouped[qid] = {"question": item.get("question", qid)}
        pipeline = item.get("pipeline", "unknown")
        grouped[qid][pipeline] = item

    return list(grouped.values())


async def run_evaluation(
    benchmark_data: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run the full evaluation across all benchmark questions."""
    results_list = _group_results_by_question(benchmark_data)

    if not results_list:
        raise ValueError("No results found in benchmark data.")

    logger.info("Found %d questions to evaluate", len(results_list))

    if dry_run:
        logger.info("[DRY RUN] Skipping LLM evaluation calls")
        evaluations = []
        for i, item in enumerate(results_list):
            question = item.get("question", f"Question {i+1}")
            evaluations.append({
                "question_index": i,
                "question": question,
                "randomized_order": "dry_run",
                "simple_scores": {
                    dim_key: 0 for dim_key, _, _ in DIMENSIONS
                },
                "agent_scores": {
                    dim_key: 0 for dim_key, _, _ in DIMENSIONS
                },
                "judge_time_ms": 0,
            })
        return _build_output(evaluations, dry_run=True)

    judge = LLMJudge()
    evaluations = []

    try:
        for i, item in enumerate(results_list):
            question = item.get("question", f"Question {i+1}")

            # Extract pipeline results
            simple_data = item.get("simple", {})
            agent_data = item.get("agent", {})

            simple_text = extract_response_text(simple_data)
            agent_text = extract_response_text(agent_data)

            logger.info(
                "Q%d: simple=%d chars, agent=%d chars",
                i + 1,
                len(simple_text),
                len(agent_text),
            )

            eval_result = await evaluate_single_question(
                judge, question, simple_text, agent_text, i
            )
            evaluations.append(eval_result)

            # Brief pause to respect rate limits
            if i < len(results_list) - 1:
                await asyncio.sleep(1.0)

    finally:
        logger.info(
            "Judge tokens used: input=%d, output=%d",
            judge.total_input_tokens,
            judge.total_output_tokens,
        )
        await judge.close()

    return _build_output(
        evaluations,
        input_tokens=judge.total_input_tokens,
        output_tokens=judge.total_output_tokens,
    )


# ---------------------------------------------------------------------------
# Aggregate scoring and output
# ---------------------------------------------------------------------------

def _build_output(
    evaluations: List[Dict[str, Any]],
    dry_run: bool = False,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Dict[str, Any]:
    """Build the final output dict with per-question and aggregate scores."""

    # Compute aggregates
    simple_agg = {dim_key: [] for dim_key, _, _ in DIMENSIONS}
    agent_agg = {dim_key: [] for dim_key, _, _ in DIMENSIONS}

    for ev in evaluations:
        for dim_key, _, _ in DIMENSIONS:
            s_val = ev["simple_scores"].get(dim_key, 0)
            a_val = ev["agent_scores"].get(dim_key, 0)
            if s_val > 0:
                simple_agg[dim_key].append(s_val)
            if a_val > 0:
                agent_agg[dim_key].append(a_val)

    def avg(vals: List[int]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    simple_averages = {dim_key: avg(simple_agg[dim_key]) for dim_key, _, _ in DIMENSIONS}
    agent_averages = {dim_key: avg(agent_agg[dim_key]) for dim_key, _, _ in DIMENSIONS}

    simple_total = avg([v for vals in simple_agg.values() for v in vals])
    agent_total = avg([v for vals in agent_agg.values() for v in vals])

    # Per-question winners
    simple_wins = 0
    agent_wins = 0
    ties = 0
    for ev in evaluations:
        s_sum = sum(ev["simple_scores"].get(d, 0) for d, _, _ in DIMENSIONS)
        a_sum = sum(ev["agent_scores"].get(d, 0) for d, _, _ in DIMENSIONS)
        if s_sum > a_sum:
            simple_wins += 1
        elif a_sum > s_sum:
            agent_wins += 1
        else:
            ties += 1

    return {
        "metadata": {
            "dry_run": dry_run,
            "num_questions": len(evaluations),
            "judge_model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "judge_input_tokens": input_tokens,
            "judge_output_tokens": output_tokens,
            "dimensions": [
                {"key": dim_key, "name_cn": name_cn, "description": desc}
                for dim_key, name_cn, desc in DIMENSIONS
            ],
        },
        "aggregate": {
            "simple_pipeline": {
                "scores": simple_averages,
                "overall": simple_total,
            },
            "agent_pipeline": {
                "scores": agent_averages,
                "overall": agent_total,
            },
            "winner": (
                "agent" if agent_total > simple_total
                else "simple" if simple_total > agent_total
                else "tie"
            ),
            "wins": {
                "simple": simple_wins,
                "agent": agent_wins,
                "tie": ties,
            },
        },
        "per_question": evaluations,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_comparison_table(output: Dict[str, Any]) -> None:
    """Print a formatted comparison table to stdout."""
    agg = output["aggregate"]
    evaluations = output["per_question"]
    dry_run = output["metadata"]["dry_run"]

    # Header
    print()
    print("=" * 78)
    print("  QUALITY EVALUATION RESULTS")
    if dry_run:
        print("  [DRY RUN - no actual evaluation performed]")
    print("=" * 78)
    print()

    # Aggregate scores table
    print("AGGREGATE SCORES (average across all questions)")
    print("-" * 72)
    print(f"{'Dimension':<28} {'Simple':<12} {'Agent':<12} {'Winner':<12}")
    print("-" * 72)

    for dim_key, name_cn, _ in DIMENSIONS:
        s = agg["simple_pipeline"]["scores"].get(dim_key, 0)
        a = agg["agent_pipeline"]["scores"].get(dim_key, 0)
        winner = (
            "Agent" if a > s
            else "Simple" if s > a
            else "Tie"
        )
        marker = " <-" if winner != "Tie" else ""
        label = f"{name_cn} ({dim_key})"
        print(f"{label:<28} {s:<12.2f} {a:<12.2f} {winner}{marker}")

    print("-" * 72)
    s_total = agg["simple_pipeline"]["overall"]
    a_total = agg["agent_pipeline"]["overall"]
    overall_winner = agg["winner"].upper()
    print(f"{'OVERALL':<28} {s_total:<12.2f} {a_total:<12.2f} {overall_winner}")
    print()

    # Win/Loss/Tie summary
    wins = agg["wins"]
    print(f"Win record: Simple {wins['simple']} | Agent {wins['agent']} | Tie {wins['tie']}")
    print()

    # Per-question breakdown
    print("PER-QUESTION BREAKDOWN")
    print("-" * 78)
    print(f"{'#':<4} {'Question':<36} {'Simple':<10} {'Agent':<10} {'Winner':<10}")
    print("-" * 78)

    for ev in evaluations:
        idx = ev["question_index"] + 1
        q = ev["question"]
        if len(q) > 34:
            q = q[:31] + "..."

        s_sum = sum(ev["simple_scores"].get(d, 0) for d, _, _ in DIMENSIONS)
        a_sum = sum(ev["agent_scores"].get(d, 0) for d, _, _ in DIMENSIONS)
        winner = "Agent" if a_sum > s_sum else "Simple" if s_sum > a_sum else "Tie"

        print(f"{idx:<4} {q:<36} {s_sum:<10} {a_sum:<10} {winner:<10}")

    print("-" * 78)
    print()

    # Comments
    for ev in evaluations:
        idx = ev["question_index"] + 1
        s_comment = ev["simple_scores"].get("brief_comment", "")
        a_comment = ev["agent_scores"].get("brief_comment", "")
        if s_comment or a_comment:
            print(f"Q{idx}: {ev['question'][:60]}")
            if s_comment:
                print(f"  Simple: {s_comment}")
            if a_comment:
                print(f"  Agent:  {a_comment}")
            print()

    # Token usage
    meta = output["metadata"]
    if meta["judge_input_tokens"] > 0:
        print(
            f"Judge token usage: "
            f"input={meta['judge_input_tokens']}, "
            f"output={meta['judge_output_tokens']}"
        )
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate chat pipeline quality using LLM-as-judge"
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"Path to benchmark results JSON (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Path to save evaluation results (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate setup without making LLM calls",
    )
    args = parser.parse_args()

    # Load benchmark results
    logger.info("Loading benchmark results from %s", args.input)
    benchmark_data = load_benchmark_results(args.input)

    # Run evaluation
    output = await run_evaluation(benchmark_data, dry_run=args.dry_run)

    # Save results
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("Evaluation results saved to %s", output_path)

    # Print table
    print_comparison_table(output)


if __name__ == "__main__":
    asyncio.run(main())
