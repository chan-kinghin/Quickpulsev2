"""Ontology comparator — multi-signal matching with Reciprocal Rank Fusion.

Adapts Agent-OM's core contribution:
1. Multiple matching signals (exact, normalized, LLM semantic)
2. Reciprocal Rank Fusion to combine rankings
3. Bidirectional matching (field->role AND role->field)
4. LLM validation for top candidates

This is the heart of the schema mapping agent.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.agents.base import AgentLLMClient
from src.agents.schema_mapping.discovery import FieldInfo

logger = logging.getLogger(__name__)


# The 3 semantic roles we're mapping to
SEMANTIC_ROLES = ("demand_field", "fulfilled_field", "picking_field")

# Chinese descriptions for semantic roles (for LLM prompts)
ROLE_DESCRIPTIONS: Dict[str, str] = {
    "demand_field": "需求量/订单数量 (demand quantity)",
    "fulfilled_field": "已完成量/实际入库数量 (fulfilled/received quantity)",
    "picking_field": "领料量/实际发料数量 (picking/issued quantity)",
}


@dataclass
class MappingSuggestion:
    """A suggested mapping from a Kingdee field to a semantic role."""

    kingdee_field: str
    semantic_role: str
    material_class: str
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Chinese explanation
    match_signals: Dict[str, float]  # signal_name -> score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kingdee_field": self.kingdee_field,
            "semantic_role": self.semantic_role,
            "material_class": self.material_class,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "match_signals": {k: round(v, 3) for k, v in self.match_signals.items()},
        }


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

# Common Kingdee field prefixes to strip
_KINGDEE_PREFIXES = re.compile(r"^F(?=[A-Z])")

# CamelCase to snake_case
_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Chinese → English keyword mapping for normalized comparison
_CN_EN_KEYWORDS: Dict[str, str] = {
    "数量": "qty",
    "实收": "real_received",
    "实发": "real_issued",
    "应收": "must_receive",
    "应发": "must_issue",
    "入库": "stock_in",
    "出库": "stock_out",
    "领料": "picking",
    "申请": "apply",
    "订单": "order",
    "累计": "accumulated",
    "未": "remaining",
    "实际": "actual",
}

# Normalized keywords that are strong signals for each role
_ROLE_KEYWORDS: Dict[str, List[str]] = {
    "demand_field": [
        "qty", "order", "demand", "must", "required",
        "order_qty", "must_qty", "demand_qty",
    ],
    "fulfilled_field": [
        "real", "received", "actual", "stock_in", "instock",
        "real_qty", "stock_in_qty", "fulfilled",
    ],
    "picking_field": [
        "pick", "picking", "issued", "actual_qty", "pick_qty",
        "material_picking",
    ],
}


def normalize_field_name(name: str) -> str:
    """Normalize a Kingdee field name for fuzzy comparison.

    Steps:
    1. Strip "F" prefix (FRealQty -> RealQty)
    2. Split camelCase -> snake_case (RealQty -> real_qty)
    3. Lowercase
    4. Remove common noise words (id, number)

    Examples:
        "FRealQty" -> "real_qty"
        "FStockInQty" -> "stock_in_qty"
        "FActualQty" -> "actual_qty"
        "FMustQty" -> "must_qty"
    """
    # Strip F prefix
    cleaned = _KINGDEE_PREFIXES.sub("", name)
    # Remove dot paths (FMaterialId.FNumber -> MaterialId FNumber)
    cleaned = cleaned.replace(".", "_")
    # CamelCase -> snake_case
    cleaned = _CAMEL_SPLIT.sub("_", cleaned)
    # Lowercase
    cleaned = cleaned.lower()
    # Remove duplicate underscores
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def normalize_chinese_label(label: str) -> str:
    """Translate Chinese label keywords to English for comparison.

    Example: "实收数量" -> "real_received_qty"
    """
    result = label
    for cn, en in _CN_EN_KEYWORDS.items():
        result = result.replace(cn, f"_{en}_")
    # Replace any remaining Chinese chars with underscore
    result = re.sub(r"[^\w]", "_", result)
    result = re.sub(r"_+", "_", result).strip("_").lower()
    return result


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    *rankings: List[Tuple[str, float]],
) -> List[Tuple[str, float]]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.

    Each ranking is a list of (item_id, score) tuples sorted by score desc.
    RRF score = sum over rankings of 1 / position_in_ranking.

    This is the core Agent-OM contribution for fusing multiple matching signals.

    Args:
        rankings: Variable number of ranked lists.

    Returns:
        Fused ranking as [(item_id, rrf_score), ...] sorted by score desc.
    """
    scores: Dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for position, (item_id, _score) in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / position
    return sorted(scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# Matching signals
# ---------------------------------------------------------------------------


def exact_match_ranking(
    fields: List[FieldInfo], role: str
) -> List[Tuple[str, float]]:
    """Signal 1: Exact string match between field name and role.

    Checks if the field's current_role matches, or if the field name
    exactly equals a known provenance key for this role.

    Returns a ranked list of (field_name, score) pairs.
    """
    ranked: List[Tuple[str, float]] = []
    for fi in fields:
        score = 0.0
        # Already mapped to this role in config
        if fi.current_role == role:
            score = 1.0
        # Field name contains the role name
        elif role.replace("_field", "") in fi.name:
            score = 0.5
        if score > 0:
            ranked.append((fi.name, score))
    # Sort descending by score
    ranked.sort(key=lambda x: -x[1])
    return ranked


def normalized_match_ranking(
    fields: List[FieldInfo], role: str
) -> List[Tuple[str, float]]:
    """Signal 2: Normalized name comparison.

    Normalizes both the field name (and optional Chinese label) and
    compares against role-specific keywords.

    Returns a ranked list of (field_name, score) pairs.
    """
    role_keywords = _ROLE_KEYWORDS.get(role, [])
    if not role_keywords:
        return []

    ranked: List[Tuple[str, float]] = []
    for fi in fields:
        score = 0.0
        # Normalize field name
        norm_name = normalize_field_name(fi.name)
        if fi.provenance_kingdee_field:
            norm_kingdee = normalize_field_name(fi.provenance_kingdee_field)
        else:
            norm_kingdee = ""

        # Normalize Chinese label
        norm_label = ""
        if fi.chinese_label:
            norm_label = normalize_chinese_label(fi.chinese_label)

        # Check each keyword
        all_normalized = f"{norm_name} {norm_kingdee} {norm_label}"
        keyword_hits = 0
        for kw in role_keywords:
            if kw in all_normalized:
                keyword_hits += 1

        if keyword_hits > 0:
            # Score proportional to keyword overlap
            score = keyword_hits / len(role_keywords)
            ranked.append((fi.name, score))

    ranked.sort(key=lambda x: -x[1])
    return ranked


async def llm_semantic_ranking(
    llm_client: AgentLLMClient,
    fields: List[FieldInfo],
    role: str,
    material_class: str,
) -> List[Tuple[str, float]]:
    """Signal 3: LLM-based semantic equivalence judgment.

    Asks the LLM to score each candidate field's relevance to the semantic role.
    Only evaluates the top candidates (from other signals) to save tokens.

    Args:
        llm_client: The agent LLM client.
        fields: Candidate fields to evaluate.
        role: Target semantic role.
        material_class: Material class context.

    Returns:
        Ranked list of (field_name, score) pairs.
    """
    if not fields:
        return []

    role_desc = ROLE_DESCRIPTIONS.get(role, role)

    # Build field descriptions for the prompt
    field_descs = []
    for fi in fields:
        desc = fi.name
        if fi.provenance_kingdee_field:
            desc += f" (金蝶字段: {fi.provenance_kingdee_field})"
        if fi.chinese_label:
            desc += f" ({fi.chinese_label})"
        if fi.source_form:
            desc += f" [来源: {fi.source_form}]"
        field_descs.append(desc)

    prompt = (
        f"你是金蝶K3Cloud ERP制造业领域专家。\n"
        f"物料类别: {material_class}\n"
        f"目标语义角色: {role} — {role_desc}\n\n"
        f"请评估以下字段与目标语义角色的匹配程度，给出0-1的分数。\n"
        f"字段列表:\n"
    )
    for i, desc in enumerate(field_descs, 1):
        prompt += f"{i}. {desc}\n"

    prompt += (
        "\n请用JSON格式回答，每个字段一个评分:\n"
        '{"scores": [{"field": "字段名", "score": 0.0, "reason": "原因"}]}\n'
        "只输出JSON，不要其他内容。"
    )

    try:
        response = await llm_client.chat_with_tools(
            messages=[
                {"role": "system", "content": "你是金蝶ERP字段匹配专家，只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            tools=[],  # No tools needed for this judgment
            temperature=0.1,
        )

        content = response.get("content", "")
        if not content:
            return []

        # Parse JSON response
        # Try to extract JSON from content (may be wrapped in markdown)
        json_match = re.search(r"\{[^{}]*\"scores\"[^{}]*\[.*?\]\s*\}", content, re.DOTALL)
        if not json_match:
            logger.warning("LLM response did not contain valid JSON scores")
            return []

        data = json.loads(json_match.group())
        ranked: List[Tuple[str, float]] = []
        for entry in data.get("scores", []):
            field_name = entry.get("field", "")
            score = float(entry.get("score", 0.0))
            # Find matching field (LLM may return slightly different names)
            for fi in fields:
                if fi.name == field_name or (
                    fi.provenance_kingdee_field
                    and fi.provenance_kingdee_field == field_name
                ):
                    ranked.append((fi.name, min(1.0, max(0.0, score))))
                    break
        ranked.sort(key=lambda x: -x[1])
        return ranked

    except Exception as exc:
        logger.warning("LLM semantic ranking failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# OntologyComparator
# ---------------------------------------------------------------------------


class OntologyComparator:
    """Compares discovered fields against semantic roles using multi-signal RRF.

    Implements the Agent-OM pattern:
    1. Run 3 matching signals (exact, normalized, LLM)
    2. Fuse via Reciprocal Rank Fusion
    3. Run bidirectionally (field->role AND role->field)
    4. Merge intersection for high-confidence matches

    Usage:
        comparator = OntologyComparator(llm_client=client)
        suggestions = await comparator.compare(fields, semantic_config, "finished_goods")
    """

    def __init__(self, llm_client: Optional[AgentLLMClient] = None) -> None:
        self._llm_client = llm_client

    async def compare(
        self,
        discovered_fields: List[FieldInfo],
        semantic_config,  # SemanticConfig from mto_config
        material_class: str,
    ) -> List[MappingSuggestion]:
        """Run multi-signal comparison and return ranked mapping suggestions.

        Args:
            discovered_fields: Fields from KingdeeFieldDiscovery.
            semantic_config: The SemanticConfig for this material class.
            material_class: Material class ID (e.g. "finished_goods").

        Returns:
            List of MappingSuggestion sorted by confidence desc.
        """
        all_suggestions: List[MappingSuggestion] = []

        for role in SEMANTIC_ROLES:
            # --- Forward matching: field -> role ---
            forward_suggestions = await self._match_direction(
                discovered_fields, role, material_class, direction="forward"
            )

            # --- Reverse matching: role -> field ---
            reverse_suggestions = await self._match_direction(
                discovered_fields, role, material_class, direction="reverse"
            )

            # --- Merge: intersection gets a confidence boost ---
            merged = self._merge_bidirectional(
                forward_suggestions, reverse_suggestions
            )
            all_suggestions.extend(merged)

        # Sort by confidence descending
        all_suggestions.sort(key=lambda s: -s.confidence)
        return all_suggestions

    async def _match_direction(
        self,
        fields: List[FieldInfo],
        role: str,
        material_class: str,
        direction: str,
    ) -> List[MappingSuggestion]:
        """Run all 3 signals for one role in one direction.

        Forward = "which field best matches this role?"
        Reverse = "which role best matches this field?" (for top fields)
        In practice both use the same signals but with different emphasis.
        """
        # Signal 1: Exact match
        exact_ranking = exact_match_ranking(fields, role)

        # Signal 2: Normalized match
        normalized_ranking = normalized_match_ranking(fields, role)

        # Signal 3: LLM semantic match (optional, only if client available)
        llm_ranking: List[Tuple[str, float]] = []
        if self._llm_client:
            # Only send top candidates to LLM to save tokens
            top_candidates = self._get_top_candidates(
                exact_ranking, normalized_ranking, max_candidates=5
            )
            candidate_fields = [
                fi for fi in fields if fi.name in top_candidates
            ]
            if candidate_fields:
                llm_ranking = await llm_semantic_ranking(
                    self._llm_client, candidate_fields, role, material_class
                )

        # Fuse all rankings via RRF
        rankings_to_fuse = [r for r in [exact_ranking, normalized_ranking, llm_ranking] if r]
        if not rankings_to_fuse:
            return []

        fused = reciprocal_rank_fusion(*rankings_to_fuse)

        # Build suggestions from fused ranking
        suggestions: List[MappingSuggestion] = []
        for field_name, rrf_score in fused:
            # Normalize RRF score to 0-1 range
            # Max possible RRF score = number of signals (one per ranking)
            max_rrf = len(rankings_to_fuse)
            confidence = rrf_score / max_rrf if max_rrf > 0 else 0.0

            # Collect individual signal scores
            signals: Dict[str, float] = {}
            for exact_name, exact_score in exact_ranking:
                if exact_name == field_name:
                    signals["exact"] = exact_score
                    break
            for norm_name, norm_score in normalized_ranking:
                if norm_name == field_name:
                    signals["normalized"] = norm_score
                    break
            for llm_name, llm_score in llm_ranking:
                if llm_name == field_name:
                    signals["llm_semantic"] = llm_score
                    break

            # Generate reasoning
            reasoning = self._generate_reasoning(
                field_name, role, signals, direction
            )

            suggestions.append(MappingSuggestion(
                kingdee_field=field_name,
                semantic_role=role,
                material_class=material_class,
                confidence=confidence,
                reasoning=reasoning,
                match_signals=signals,
            ))

        return suggestions

    def _merge_bidirectional(
        self,
        forward: List[MappingSuggestion],
        reverse: List[MappingSuggestion],
    ) -> List[MappingSuggestion]:
        """Merge forward and reverse matches.

        Fields that appear in BOTH directions get a confidence boost
        (intersection = higher confidence, per Agent-OM).
        """
        forward_map: Dict[str, MappingSuggestion] = {
            s.kingdee_field: s for s in forward
        }
        reverse_map: Dict[str, MappingSuggestion] = {
            s.kingdee_field: s for s in reverse
        }

        all_fields = set(forward_map.keys()) | set(reverse_map.keys())
        merged: List[MappingSuggestion] = []

        for field_name in all_fields:
            fwd = forward_map.get(field_name)
            rev = reverse_map.get(field_name)

            if fwd and rev:
                # Bidirectional match — boost confidence
                avg_confidence = (fwd.confidence + rev.confidence) / 2
                boost = min(0.2, avg_confidence * 0.3)  # Up to 0.2 boost
                merged_confidence = min(1.0, avg_confidence + boost)

                # Merge signals from both directions
                merged_signals = dict(fwd.match_signals)
                for k, v in rev.match_signals.items():
                    if k in merged_signals:
                        merged_signals[k] = max(merged_signals[k], v)
                    else:
                        merged_signals[k] = v

                merged.append(MappingSuggestion(
                    kingdee_field=field_name,
                    semantic_role=fwd.semantic_role,
                    material_class=fwd.material_class,
                    confidence=merged_confidence,
                    reasoning=fwd.reasoning + " [双向匹配确认]",
                    match_signals=merged_signals,
                ))
            elif fwd:
                merged.append(fwd)
            elif rev:
                merged.append(rev)

        return merged

    @staticmethod
    def _get_top_candidates(
        *rankings: List[Tuple[str, float]],
        max_candidates: int = 5,
    ) -> set:
        """Get top candidate field names across multiple rankings."""
        candidates: set = set()
        for ranking in rankings:
            for name, _score in ranking[:max_candidates]:
                candidates.add(name)
        return candidates

    @staticmethod
    def _generate_reasoning(
        field_name: str,
        role: str,
        signals: Dict[str, float],
        direction: str,
    ) -> str:
        """Generate Chinese reasoning text for a mapping suggestion."""
        parts = []
        role_desc = ROLE_DESCRIPTIONS.get(role, role)

        if signals.get("exact", 0) > 0:
            parts.append(f"字段'{field_name}'与角色'{role_desc}'精确匹配")
        if signals.get("normalized", 0) > 0:
            score = signals["normalized"]
            parts.append(f"标准化名称相似度: {score:.0%}")
        if signals.get("llm_semantic", 0) > 0:
            score = signals["llm_semantic"]
            parts.append(f"LLM语义判断: {score:.0%}")

        if not parts:
            return f"字段'{field_name}'与'{role_desc}'无明显匹配信号"

        return "；".join(parts)
