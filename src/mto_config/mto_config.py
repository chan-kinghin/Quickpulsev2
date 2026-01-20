"""MTO Configuration Loader - Configurable material class mappings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ColumnConfig:
    """Configuration for a single column's data source."""

    source: Optional[str] = None
    data_field: Optional[str] = None  # Renamed from 'field' to avoid shadowing dataclasses.field
    match_by: list[str] = field(default_factory=list)
    calculated: Optional[str] = None
    subtract: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ColumnConfig":
        return cls(
            source=data.get("source"),
            data_field=data.get("field"),
            match_by=data.get("match_by", []),
            calculated=data.get("calculated"),
            subtract=data.get("subtract"),
        )


@dataclass
class MaterialClassConfig:
    """Configuration for a material class (e.g., 07.xx.xxx finished goods)."""

    id: str
    pattern: re.Pattern
    display_name: str
    material_type: int
    source_form: str
    mto_field: str
    columns: dict[str, ColumnConfig]
    item_fields: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict) -> "MaterialClassConfig":
        return cls(
            id=data["id"],
            pattern=re.compile(data["pattern"]),
            display_name=data["display_name"],
            material_type=data.get("material_type", 1),
            source_form=data["source_form"],
            mto_field=data["mto_field"],
            columns={
                k: ColumnConfig.from_dict(v) for k, v in data["columns"].items()
            },
            item_fields=data["item_fields"],
        )

    def matches(self, material_code: str) -> bool:
        """Check if this config applies to the given material code."""
        return bool(self.pattern.match(material_code))


@dataclass
class ReceiptSourceConfig:
    """Configuration for a receipt data source."""

    form_id: str
    mto_field: str
    qty_field: str
    material_field: str
    link_field: Optional[str] = None
    app_qty_field: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ReceiptSourceConfig":
        return cls(
            form_id=data["form_id"],
            mto_field=data["mto_field"],
            qty_field=data["qty_field"],
            material_field=data["material_field"],
            link_field=data.get("link_field"),
            app_qty_field=data.get("app_qty_field"),
        )


class MTOConfig:
    """MTO Configuration manager.

    Loads and provides access to configurable material class mappings
    and column definitions from a JSON config file.

    Example usage:
        config = MTOConfig("config/mto_config.json")
        class_config = config.get_class_for_material("07.02.037")
        if class_config:
            print(f"Material class: {class_config.display_name}")
            print(f"Source form: {class_config.source_form}")
    """

    def __init__(self, config_path: str = "config/mto_config.json"):
        self._config_path = Path(config_path)
        self._material_classes: list[MaterialClassConfig] = []
        self._receipt_sources: dict[str, ReceiptSourceConfig] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from JSON file."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"MTO config file not found: {self._config_path}")

        with open(self._config_path, encoding="utf-8") as f:
            data = json.load(f)

        self._material_classes = [
            MaterialClassConfig.from_dict(mc) for mc in data.get("material_classes", [])
        ]
        self._receipt_sources = {
            k: ReceiptSourceConfig.from_dict(v)
            for k, v in data.get("receipt_sources", {}).items()
        }

    def reload(self) -> None:
        """Reload configuration from file (useful for hot-reloading)."""
        self._load_config()

    def get_class_for_material(self, material_code: str) -> Optional[MaterialClassConfig]:
        """Find the configuration for a material code based on pattern matching.

        Args:
            material_code: The material code to look up (e.g., "07.02.037")

        Returns:
            MaterialClassConfig if a matching pattern is found, None otherwise
        """
        for mc in self._material_classes:
            if mc.matches(material_code):
                return mc
        return None

    def get_receipt_source(self, source_name: str) -> Optional[ReceiptSourceConfig]:
        """Get receipt source configuration by name.

        Args:
            source_name: Name of the receipt source (e.g., "PRD_INSTOCK")

        Returns:
            ReceiptSourceConfig if found, None otherwise
        """
        return self._receipt_sources.get(source_name)

    @property
    def material_classes(self) -> list[MaterialClassConfig]:
        """Get all configured material classes."""
        return self._material_classes

    @property
    def receipt_sources(self) -> dict[str, ReceiptSourceConfig]:
        """Get all configured receipt sources."""
        return self._receipt_sources

    def get_all_source_forms(self) -> set[str]:
        """Get all unique source forms referenced in the config."""
        forms = {mc.source_form for mc in self._material_classes}
        for mc in self._material_classes:
            for col in mc.columns.values():
                if col.source:
                    forms.add(col.source)
        return forms
