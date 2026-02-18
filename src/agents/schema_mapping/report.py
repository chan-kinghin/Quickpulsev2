"""Mapping report generator — human-readable output from mapping suggestions.

Generates markdown reports grouped by material class, showing confidence
scores, match signals, and diffs against the current configuration.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.schema_mapping.comparator import (
    MappingSuggestion,
    ROLE_DESCRIPTIONS,
    SEMANTIC_ROLES,
)

logger = logging.getLogger(__name__)


class MappingReport:
    """Generates human-readable reports from mapping suggestions.

    Usage:
        report = MappingReport()
        markdown = report.generate_report(suggestions)
        diff = report.generate_diff(suggestions, current_config)
    """

    def generate_report(
        self,
        suggestions: List[MappingSuggestion],
        title: Optional[str] = None,
    ) -> str:
        """Generate a markdown report from mapping suggestions.

        Groups suggestions by material class and semantic role,
        highlights high-confidence matches and unmatched fields.

        Args:
            suggestions: List of MappingSuggestion from OntologyComparator.
            title: Optional report title.

        Returns:
            Markdown-formatted report string.
        """
        if not suggestions:
            return "# Schema Mapping Report\n\nNo mapping suggestions generated."

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not title:
            title = "Schema Mapping Report"

        lines = [
            f"# {title}",
            f"Generated: {now}",
            "",
        ]

        # Group by material class
        by_class: Dict[str, List[MappingSuggestion]] = {}
        for s in suggestions:
            by_class.setdefault(s.material_class, []).append(s)

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Material classes analyzed: {len(by_class)}")
        lines.append(f"- Total suggestions: {len(suggestions)}")
        high_conf = [s for s in suggestions if s.confidence >= 0.7]
        lines.append(f"- High confidence (>=0.7): {len(high_conf)}")
        low_conf = [s for s in suggestions if s.confidence < 0.3]
        lines.append(f"- Low confidence (<0.3): {len(low_conf)}")
        lines.append("")

        # Per-class details
        for class_id, class_suggestions in sorted(by_class.items()):
            lines.append(f"## Material Class: {class_id}")
            lines.append("")

            # Group by role
            by_role: Dict[str, List[MappingSuggestion]] = {}
            for s in class_suggestions:
                by_role.setdefault(s.semantic_role, []).append(s)

            for role in SEMANTIC_ROLES:
                role_suggestions = by_role.get(role, [])
                role_desc = ROLE_DESCRIPTIONS.get(role, role)
                lines.append(f"### {role} ({role_desc})")
                lines.append("")

                if not role_suggestions:
                    lines.append("_No candidates found_")
                    lines.append("")
                    continue

                # Table header
                lines.append("| Rank | Field | Confidence | Signals | Reasoning |")
                lines.append("| --- | --- | --- | --- | --- |")

                # Sort by confidence desc
                role_suggestions.sort(key=lambda s: -s.confidence)
                for rank, s in enumerate(role_suggestions, 1):
                    conf_pct = f"{s.confidence:.0%}"
                    conf_badge = _confidence_badge(s.confidence)
                    signals = ", ".join(
                        f"{k}={v:.2f}" for k, v in sorted(s.match_signals.items())
                    )
                    # Truncate reasoning for table
                    reason_short = s.reasoning[:60] + "..." if len(s.reasoning) > 60 else s.reasoning
                    lines.append(
                        f"| {rank} | `{s.kingdee_field}` | {conf_badge} {conf_pct} "
                        f"| {signals} | {reason_short} |"
                    )

                lines.append("")

            # Best matches summary for this class
            lines.append(f"### Best Matches for {class_id}")
            lines.append("")
            for role in SEMANTIC_ROLES:
                role_suggestions = by_role.get(role, [])
                if role_suggestions:
                    best = max(role_suggestions, key=lambda s: s.confidence)
                    lines.append(
                        f"- **{role}**: `{best.kingdee_field}` "
                        f"(confidence: {best.confidence:.0%})"
                    )
                else:
                    lines.append(f"- **{role}**: _no match_")
            lines.append("")

        return "\n".join(lines)

    def generate_diff(
        self,
        suggestions: List[MappingSuggestion],
        current_config: Dict[str, Any],
    ) -> str:
        """Generate a diff showing what would change vs current config.

        Compares the top suggestion for each role against the current
        semantic config to highlight additions, changes, and confirmations.

        Args:
            suggestions: Mapping suggestions.
            current_config: The current mto_config.json semantic sections.

        Returns:
            Markdown diff report.
        """
        lines = [
            "# Configuration Diff Report",
            "",
        ]

        # Group suggestions by class
        by_class: Dict[str, List[MappingSuggestion]] = {}
        for s in suggestions:
            by_class.setdefault(s.material_class, []).append(s)

        for class_id, class_suggestions in sorted(by_class.items()):
            lines.append(f"## {class_id}")
            lines.append("")

            # Get current semantic config for this class
            current_semantic = self._get_current_semantic(
                current_config, class_id
            )

            # Find best suggestion per role
            best_per_role: Dict[str, MappingSuggestion] = {}
            for s in class_suggestions:
                if s.semantic_role not in best_per_role or s.confidence > best_per_role[s.semantic_role].confidence:
                    best_per_role[s.semantic_role] = s

            for role in SEMANTIC_ROLES:
                current_value = current_semantic.get(role)
                suggestion = best_per_role.get(role)

                if suggestion and current_value:
                    if suggestion.kingdee_field == current_value:
                        lines.append(
                            f"  {role}: `{current_value}` "
                            f"(CONFIRMED, confidence: {suggestion.confidence:.0%})"
                        )
                    else:
                        lines.append(
                            f"  {role}: `{current_value}` -> `{suggestion.kingdee_field}` "
                            f"(CHANGE suggested, confidence: {suggestion.confidence:.0%})"
                        )
                elif suggestion and not current_value:
                    lines.append(
                        f"  {role}: _none_ -> `{suggestion.kingdee_field}` "
                        f"(NEW mapping, confidence: {suggestion.confidence:.0%})"
                    )
                elif current_value and not suggestion:
                    lines.append(
                        f"  {role}: `{current_value}` "
                        f"(no alternative found)"
                    )
                else:
                    lines.append(f"  {role}: _unmapped_")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _get_current_semantic(
        config: Dict[str, Any], class_id: str
    ) -> Dict[str, str]:
        """Extract current semantic field values for a material class."""
        for mc in config.get("material_classes", []):
            if mc.get("id") == class_id:
                sem = mc.get("semantic", {})
                return {
                    "demand_field": sem.get("demand_field"),
                    "fulfilled_field": sem.get("fulfilled_field"),
                    "picking_field": sem.get("picking_field"),
                }
        return {}


def _confidence_badge(confidence: float) -> str:
    """Return a text badge based on confidence level."""
    if confidence >= 0.8:
        return "[HIGH]"
    elif confidence >= 0.5:
        return "[MED]"
    elif confidence >= 0.3:
        return "[LOW]"
    else:
        return "[WEAK]"
