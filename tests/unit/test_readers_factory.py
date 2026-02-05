"""Tests for src/readers/factory.py"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.readers.factory import (
    PRODUCTION_BOM_CONFIG,
    PRODUCTION_ORDER_CONFIG,
    PRODUCTION_RECEIPT_CONFIG,
    PURCHASE_ORDER_CONFIG,
    PURCHASE_RECEIPT_CONFIG,
    SALES_DELIVERY_CONFIG,
    SALES_ORDER_CONFIG,
    SUBCONTRACTING_ORDER_CONFIG,
    FieldMapping,
    GenericReader,
    ProductionBOMReader,
    ProductionOrderReader,
    ProductionReceiptReader,
    PurchaseOrderReader,
    PurchaseReceiptReader,
    SubcontractingOrderReader,
    _decimal,
    _int,
    _optional_str,
    _str,
)
from tests.fixtures.sample_data import (
    SAMPLE_BOM_ENTRIES_RAW,
    SAMPLE_PRODUCTION_ORDER_RAW,
)


class TestFieldConverters:
    """Test field converter functions."""

    def test_str_converter_with_value(self):
        """Test _str converter with value."""
        assert _str("hello") == "hello"
        assert _str("test value") == "test value"

    def test_str_converter_with_none(self):
        """Test _str converter with None."""
        assert _str(None) == ""

    def test_str_converter_with_empty(self):
        """Test _str converter with empty string."""
        assert _str("") == ""

    def test_str_converter_with_number(self):
        """Test _str converter with number (non-None passthrough)."""
        # Note: _str returns the value as-is if not falsy
        assert _str(123) == 123

    def test_decimal_converter_with_string(self):
        """Test _decimal converter with string."""
        assert _decimal("100.5") == Decimal("100.5")
        assert _decimal("0") == Decimal("0")

    def test_decimal_converter_with_int(self):
        """Test _decimal converter with int."""
        assert _decimal(100) == Decimal("100")

    def test_decimal_converter_with_float(self):
        """Test _decimal converter with float."""
        assert _decimal(100.5) == Decimal("100.5")

    def test_decimal_converter_with_none(self):
        """Test _decimal converter with None."""
        assert _decimal(None) == Decimal("0")

    def test_decimal_converter_with_zero(self):
        """Test _decimal converter with 0."""
        assert _decimal(0) == Decimal("0")

    def test_int_converter_with_int(self):
        """Test _int converter with int."""
        assert _int(5) == 5
        assert _int(0) == 0

    def test_int_converter_with_string(self):
        """Test _int converter with numeric string."""
        assert _int("10") == 10

    def test_int_converter_with_none(self):
        """Test _int converter with None."""
        assert _int(None) == 0

    def test_int_converter_with_falsy(self):
        """Test _int converter with falsy values."""
        assert _int(0) == 0
        assert _int("") == 0

    def test_optional_str_with_value(self):
        """Test _optional_str converter with value."""
        assert _optional_str("value") == "value"

    def test_optional_str_with_none(self):
        """Test _optional_str converter with None."""
        assert _optional_str(None) is None

    def test_optional_str_with_empty(self):
        """Test _optional_str converter with empty string."""
        assert _optional_str("") is None


class TestFieldMapping:
    """Tests for FieldMapping dataclass."""

    def test_basic_mapping(self):
        """Test basic field mapping."""
        mapping = FieldMapping("FBillNo")
        assert mapping.kingdee_field == "FBillNo"
        assert mapping.converter == _str  # Default
        assert mapping.fallback_field is None

    def test_mapping_with_converter(self):
        """Test mapping with custom converter."""
        mapping = FieldMapping("FQty", _decimal)
        assert mapping.converter == _decimal

    def test_mapping_with_fallback(self):
        """Test mapping with fallback field."""
        mapping = FieldMapping("FPrimaryField", _str, "FFallbackField")
        assert mapping.fallback_field == "FFallbackField"


class TestReaderConfigs:
    """Test reader configuration constants."""

    def test_production_order_config(self):
        """Test PRODUCTION_ORDER_CONFIG."""
        config = PRODUCTION_ORDER_CONFIG
        assert config.form_id == "PRD_MO"
        assert config.mto_field == "FMTONo"
        assert config.date_field == "FCreateDate"
        assert "bill_no" in config.field_mappings
        assert "mto_number" in config.field_mappings

    def test_production_bom_config(self):
        """Test PRODUCTION_BOM_CONFIG."""
        config = PRODUCTION_BOM_CONFIG
        assert config.form_id == "PRD_PPBOM"
        assert config.mto_field == "FMTONO"
        assert config.bill_field == "FMOBillNO"
        assert "material_type" in config.field_mappings

    def test_production_receipt_config(self):
        """Test PRODUCTION_RECEIPT_CONFIG."""
        config = PRODUCTION_RECEIPT_CONFIG
        assert config.form_id == "PRD_INSTOCK"
        assert config.mto_field == "FMtoNo"

    def test_purchase_order_config(self):
        """Test PURCHASE_ORDER_CONFIG."""
        config = PURCHASE_ORDER_CONFIG
        assert config.form_id == "PUR_PurchaseOrder"
        assert config.mto_field == "FMtoNo"

    def test_purchase_receipt_config(self):
        """Test PURCHASE_RECEIPT_CONFIG."""
        config = PURCHASE_RECEIPT_CONFIG
        assert config.form_id == "STK_InStock"
        assert "bill_type_number" in config.field_mappings

    def test_subcontracting_order_config(self):
        """Test SUBCONTRACTING_ORDER_CONFIG."""
        config = SUBCONTRACTING_ORDER_CONFIG
        assert config.form_id == "SUB_SUBREQORDER"

    def test_sales_delivery_config(self):
        """Test SALES_DELIVERY_CONFIG."""
        config = SALES_DELIVERY_CONFIG
        assert config.form_id == "SAL_OUTSTOCK"

    def test_sales_order_config(self):
        """Test SALES_ORDER_CONFIG."""
        config = SALES_ORDER_CONFIG
        assert config.form_id == "SAL_SaleOrder"


class TestGenericReader:
    """Tests for GenericReader class."""

    def test_field_keys_property(self, mock_kingdee_client):
        """Test field_keys property extracts Kingdee fields."""
        reader = ProductionOrderReader(mock_kingdee_client)
        keys = reader.field_keys

        assert "FBillNo" in keys
        assert "FMTONo" in keys
        assert "FMaterialId.FNumber" in keys
        assert "FQty" in keys

    def test_form_id_property(self, mock_kingdee_client):
        """Test form_id property."""
        reader = ProductionOrderReader(mock_kingdee_client)
        assert reader.form_id == "PRD_MO"

    def test_mto_field_property(self, mock_kingdee_client):
        """Test mto_field property."""
        reader = ProductionOrderReader(mock_kingdee_client)
        assert reader.mto_field == "FMTONo"

    def test_date_field_property(self, mock_kingdee_client):
        """Test date_field property."""
        reader = ProductionOrderReader(mock_kingdee_client)
        assert reader.date_field == "FCreateDate"

    def test_to_model_production_order(self, mock_kingdee_client):
        """Test raw API data to ProductionOrderModel conversion."""
        reader = ProductionOrderReader(mock_kingdee_client)
        model = reader.to_model(SAMPLE_PRODUCTION_ORDER_RAW)

        assert model.bill_no == "MO0001"
        assert model.mto_number == "AK2510034"
        assert model.workshop == "Workshop A"
        assert model.material_code == "P001"
        assert model.qty == Decimal("100")
        assert model.status == "Approved"
        assert model.create_date == "2025-01-15"

    def test_to_model_production_bom(self, mock_kingdee_client):
        """Test raw API data to ProductionBOMModel conversion."""
        reader = ProductionBOMReader(mock_kingdee_client)
        raw_data = SAMPLE_BOM_ENTRIES_RAW[0]  # Self-made entry
        model = reader.to_model(raw_data)

        assert model.mo_bill_no == "MO0001"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "C001"
        assert model.material_type == 1
        assert model.need_qty == Decimal("50")
        assert model.picked_qty == Decimal("30")
        assert model.no_picked_qty == Decimal("20")

    def test_to_model_with_missing_optional_fields(self, mock_kingdee_client):
        """Test conversion with missing optional fields."""
        reader = ProductionOrderReader(mock_kingdee_client)
        raw_data = {
            "FBillNo": "MO001",
            "FMTONo": "AK001",
            "FWorkShopID.FName": None,
            "FMaterialId.FNumber": "M001",
            "FMaterialId.FName": None,
            "FMaterialId.FSpecification": None,
            "FQty": 0,
            "FStatus": "",
            "FCreateDate": None,
        }
        model = reader.to_model(raw_data)

        assert model.bill_no == "MO001"
        assert model.workshop == ""  # Converted from None
        assert model.qty == Decimal("0")
        assert model.create_date is None

    @pytest.mark.asyncio
    async def test_fetch_by_mto(self, mock_kingdee_client):
        """Test fetch_by_mto calls client correctly."""
        reader = ProductionOrderReader(mock_kingdee_client)
        mock_kingdee_client.query_all = AsyncMock(
            return_value=[SAMPLE_PRODUCTION_ORDER_RAW]
        )

        results = await reader.fetch_by_mto("AK2510034")

        assert len(results) == 1
        assert results[0].mto_number == "AK2510034"
        mock_kingdee_client.query_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_by_mto_empty(self, mock_kingdee_client):
        """Test fetch_by_mto with no results."""
        reader = ProductionOrderReader(mock_kingdee_client)
        mock_kingdee_client.query_all = AsyncMock(return_value=[])

        results = await reader.fetch_by_mto("NONEXISTENT")

        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_by_bill_nos_empty(self, mock_kingdee_client):
        """Test fetch_by_bill_nos with empty input."""
        reader = ProductionBOMReader(mock_kingdee_client)

        results = await reader.fetch_by_bill_nos([])

        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_by_bill_nos(self, mock_kingdee_client):
        """Test fetch_by_bill_nos with bill numbers."""
        reader = ProductionBOMReader(mock_kingdee_client)
        mock_kingdee_client.query_all = AsyncMock(return_value=SAMPLE_BOM_ENTRIES_RAW)

        results = await reader.fetch_by_bill_nos(["MO0001", "MO0002"])

        assert len(results) == 3  # 3 BOM entries in sample data
        mock_kingdee_client.query_all.assert_called_once()
        call_args = mock_kingdee_client.query_all.call_args
        assert "FMOBillNO IN" in call_args.kwargs["filter_string"]

    @pytest.mark.asyncio
    async def test_fetch_by_date_range(self, mock_kingdee_client):
        """Test fetch_by_date_range."""
        from datetime import date

        reader = ProductionOrderReader(mock_kingdee_client)
        mock_kingdee_client.query_by_date_range = AsyncMock(
            return_value=[SAMPLE_PRODUCTION_ORDER_RAW]
        )

        results = await reader.fetch_by_date_range(
            date(2025, 1, 1), date(2025, 1, 15)
        )

        assert len(results) == 1
        mock_kingdee_client.query_by_date_range.assert_called_once()


class TestTypedReaders:
    """Test typed reader classes."""

    def test_production_order_reader(self, mock_kingdee_client):
        """Test ProductionOrderReader initialization."""
        reader = ProductionOrderReader(mock_kingdee_client)
        assert reader.form_id == "PRD_MO"
        assert reader.client == mock_kingdee_client

    def test_production_bom_reader(self, mock_kingdee_client):
        """Test ProductionBOMReader initialization."""
        reader = ProductionBOMReader(mock_kingdee_client)
        assert reader.form_id == "PRD_PPBOM"

    def test_production_receipt_reader(self, mock_kingdee_client):
        """Test ProductionReceiptReader initialization."""
        reader = ProductionReceiptReader(mock_kingdee_client)
        assert reader.form_id == "PRD_INSTOCK"

    def test_purchase_order_reader(self, mock_kingdee_client):
        """Test PurchaseOrderReader initialization."""
        reader = PurchaseOrderReader(mock_kingdee_client)
        assert reader.form_id == "PUR_PurchaseOrder"

    def test_purchase_receipt_reader(self, mock_kingdee_client):
        """Test PurchaseReceiptReader initialization."""
        reader = PurchaseReceiptReader(mock_kingdee_client)
        assert reader.form_id == "STK_InStock"

    def test_subcontracting_order_reader(self, mock_kingdee_client):
        """Test SubcontractingOrderReader initialization."""
        reader = SubcontractingOrderReader(mock_kingdee_client)
        assert reader.form_id == "SUB_SUBREQORDER"
