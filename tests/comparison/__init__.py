"""QuickPulse vs Kingdee data comparison test infrastructure.

This package provides tools for validating that QuickPulse UI displays
correct values compared to Kingdee raw data.

Modules:
    field_specs: Field definitions with Chinese names and validation rules
    raw_fetcher: Direct Kingdee API queries (bypasses QuickPulse readers)
    aggregator: Material-type-specific aggregation logic
    comparator: Main comparison engine

Usage:
    from tests.comparison.comparator import MTOComparator
    from tests.comparison.field_specs import FIELD_SPECS, USER_MTOS
"""
