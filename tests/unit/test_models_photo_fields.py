"""Wave A1 tests for PRD_MO photo FileID fields.

Covers ``ProductionOrderModel.photo_file_id_1/2/3`` and the
``PRODUCTION_ORDER_CONFIG`` factory mapping from
``PRD_MO.TreeEntity.F_QWJI_YSTP1/2/3``.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from src.readers.factory import (
    PRODUCTION_ORDER_CONFIG,
    ProductionOrderReader,
)
from src.readers.models import ProductionOrderModel


def _base_kwargs() -> dict:
    """Minimum required kwargs for ProductionOrderModel."""
    return {
        "bill_no": "MO260501414",
        "mto_number": "DS264102S",
        "workshop": "Workshop A",
        "material_code": "07.02.001",
        "material_name": "MARES Mask",
        "specification": "Adult",
        "qty": Decimal("100"),
        "status": "B",
    }


class TestProductionOrderModelPhotoFields:
    """ProductionOrderModel — photo_file_id_{1,2,3} fields."""

    def test_photo_fields_default_to_none(self):
        model = ProductionOrderModel(**_base_kwargs())
        assert model.photo_file_id_1 is None
        assert model.photo_file_id_2 is None
        assert model.photo_file_id_3 is None

    def test_all_three_photo_fields_set(self):
        model = ProductionOrderModel(
            **_base_kwargs(),
            photo_file_id_1="8978cffd01404da595bdc8be907fbcce",
            photo_file_id_2="d8b7e9b6fed143efae647b77c742cd67",
            photo_file_id_3="4ec577b82824455c9cb7a1aed25c85f8",
        )
        assert model.photo_file_id_1 == "8978cffd01404da595bdc8be907fbcce"
        assert model.photo_file_id_2 == "d8b7e9b6fed143efae647b77c742cd67"
        assert model.photo_file_id_3 == "4ec577b82824455c9cb7a1aed25c85f8"

    def test_partial_photo_fields(self):
        model = ProductionOrderModel(
            **_base_kwargs(),
            photo_file_id_1="8978cffd01404da595bdc8be907fbcce",
        )
        assert model.photo_file_id_1 == "8978cffd01404da595bdc8be907fbcce"
        assert model.photo_file_id_2 is None
        assert model.photo_file_id_3 is None


class TestProductionOrderConfigPhotoMappings:
    """PRODUCTION_ORDER_CONFIG — F_QWJI_YSTP{1,2,3} factory mappings."""

    def test_field_keys_include_photo_fields(self):
        reader = ProductionOrderReader(MagicMock())
        assert "F_QWJI_YSTP1" in reader.field_keys
        assert "F_QWJI_YSTP2" in reader.field_keys
        assert "F_QWJI_YSTP3" in reader.field_keys

    def test_to_model_maps_populated_photo_fields(self):
        reader = ProductionOrderReader(MagicMock())
        raw = {
            "FBillNo": "MO260501414",
            "FMTONo": "DS264102S",
            "FWorkShopID.FName": "Workshop",
            "FMaterialId.FNumber": "07.02.001",
            "FMaterialId.FName": "MARES Mask",
            "FMaterialId.FSpecification": "Adult",
            "FAuxPropId": 0,
            "FQty": 100,
            "FStatus": "B",
            "FCreateDate": "2026-05-01",
            "F_QWJI_YSTP1": "8978cffd01404da595bdc8be907fbcce",
            "F_QWJI_YSTP2": "d8b7e9b6fed143efae647b77c742cd67",
            "F_QWJI_YSTP3": "4ec577b82824455c9cb7a1aed25c85f8",
        }
        model = reader.to_model(raw)
        assert model.photo_file_id_1 == "8978cffd01404da595bdc8be907fbcce"
        assert model.photo_file_id_2 == "d8b7e9b6fed143efae647b77c742cd67"
        assert model.photo_file_id_3 == "4ec577b82824455c9cb7a1aed25c85f8"

    def test_to_model_missing_photo_fields_yields_none(self):
        reader = ProductionOrderReader(MagicMock())
        raw = {
            "FBillNo": "MO0001",
            "FMTONo": "AK2510034",
            "FWorkShopID.FName": "Workshop A",
            "FMaterialId.FNumber": "P001",
            "FMaterialId.FName": "Finished Product A",
            "FMaterialId.FSpecification": "Spec A",
            "FQty": 100,
            "FStatus": "Approved",
            "FCreateDate": "2025-01-15",
            # Photo fields intentionally absent
        }
        model = reader.to_model(raw)
        assert model.photo_file_id_1 is None
        assert model.photo_file_id_2 is None
        assert model.photo_file_id_3 is None

    def test_to_model_empty_string_photo_normalises_to_none(self):
        """Kingdee returns '' for unpopulated photo slots; _optional_str
        must turn that into None so downstream filtering is uniform."""
        reader = ProductionOrderReader(MagicMock())
        raw = {
            "FBillNo": "MO0001",
            "FMTONo": "AK2510034",
            "FWorkShopID.FName": "Workshop A",
            "FMaterialId.FNumber": "P001",
            "FMaterialId.FName": "Finished Product A",
            "FMaterialId.FSpecification": "Spec A",
            "FQty": 100,
            "FStatus": "Approved",
            "FCreateDate": "2025-01-15",
            "F_QWJI_YSTP1": "",
            "F_QWJI_YSTP2": None,
            "F_QWJI_YSTP3": "  ",  # whitespace stays — only falsy → None
        }
        model = reader.to_model(raw)
        assert model.photo_file_id_1 is None
        assert model.photo_file_id_2 is None
        # "  " is truthy — preserved as-is (real-world Kingdee uses '' or None)
        assert model.photo_file_id_3 == "  "

    def test_photo_fields_are_optional_str_converter(self):
        """Spec the converter explicitly so future changes are visible."""
        from src.readers.factory import _optional_str

        for key in ("photo_file_id_1", "photo_file_id_2", "photo_file_id_3"):
            mapping = PRODUCTION_ORDER_CONFIG.field_mappings[key]
            assert mapping.converter is _optional_str
            assert mapping.kingdee_field == f"F_QWJI_YSTP{key[-1]}"
