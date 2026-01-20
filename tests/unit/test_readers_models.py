"""Tests for src/readers/models.py"""

from decimal import Decimal
from typing import Optional

import pytest
from pydantic import ValidationError

from src.readers.models import (
    MaterialPickingModel,
    ProductionBOMModel,
    ProductionOrderModel,
    ProductionReceiptModel,
    PurchaseOrderModel,
    PurchaseReceiptModel,
    SalesDeliveryModel,
    SalesOrderModel,
    SubcontractingOrderModel,
)


class TestProductionOrderModel:
    """Tests for ProductionOrderModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = ProductionOrderModel(
            bill_no="MO001",
            mto_number="AK2510034",
            workshop="Workshop A",
            material_code="M001",
            material_name="Material",
            specification="Spec",
            qty=Decimal("100"),
            status="Approved",
        )
        assert model.bill_no == "MO001"
        assert model.mto_number == "AK2510034"
        assert model.qty == Decimal("100")

    def test_optional_fields_default(self):
        """Test optional fields have defaults."""
        model = ProductionOrderModel(
            bill_no="MO001",
            mto_number="AK2510034",
            workshop="",
            material_code="M001",
            material_name="",
            specification="",
            qty=Decimal("0"),
            status="",
        )
        assert model.aux_attributes == ""
        assert model.create_date is None

    def test_with_aux_attributes(self):
        """Test model with aux_attributes."""
        model = ProductionOrderModel(
            bill_no="MO001",
            mto_number="AK2510034",
            workshop="Workshop",
            material_code="M001",
            material_name="Material",
            specification="Spec",
            aux_attributes="Blue Model",
            qty=Decimal("100"),
            status="Approved",
        )
        assert model.aux_attributes == "Blue Model"

    def test_with_create_date(self):
        """Test model with create_date."""
        model = ProductionOrderModel(
            bill_no="MO001",
            mto_number="AK2510034",
            workshop="Workshop",
            material_code="M001",
            material_name="Material",
            specification="Spec",
            qty=Decimal("100"),
            status="Approved",
            create_date="2025-01-15",
        )
        assert model.create_date == "2025-01-15"


class TestProductionBOMModel:
    """Tests for ProductionBOMModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="Part",
            specification="Spec",
            material_type=1,
            need_qty=Decimal("10"),
            picked_qty=Decimal("5"),
            no_picked_qty=Decimal("5"),
        )
        assert model.mo_bill_no == "MO001"
        assert model.material_type == 1
        assert model.need_qty == Decimal("10")

    def test_material_type_self_made(self):
        """Test material type 1 (self-made)."""
        model = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="",
            specification="",
            material_type=1,
            need_qty=Decimal("10"),
            picked_qty=Decimal("5"),
            no_picked_qty=Decimal("5"),
        )
        assert model.material_type == 1

    def test_material_type_purchased(self):
        """Test material type 2 (purchased)."""
        model = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="",
            specification="",
            material_type=2,
            need_qty=Decimal("10"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("10"),
        )
        assert model.material_type == 2

    def test_material_type_subcontracted(self):
        """Test material type 3 (subcontracted)."""
        model = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="",
            specification="",
            material_type=3,
            need_qty=Decimal("10"),
            picked_qty=Decimal("10"),
            no_picked_qty=Decimal("0"),
        )
        assert model.material_type == 3

    def test_aux_prop_id_default(self):
        """Test aux_prop_id defaults to 0."""
        model = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="",
            specification="",
            material_type=1,
            need_qty=Decimal("10"),
            picked_qty=Decimal("5"),
            no_picked_qty=Decimal("5"),
        )
        assert model.aux_prop_id == 0

    def test_with_aux_prop_id(self):
        """Test model with aux_prop_id."""
        model = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="",
            specification="",
            aux_prop_id=1001,
            material_type=2,
            need_qty=Decimal("10"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("10"),
        )
        assert model.aux_prop_id == 1001


class TestProductionReceiptModel:
    """Tests for ProductionReceiptModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = ProductionReceiptModel(
            mto_number="AK001",
            material_code="M001",
            real_qty=Decimal("100"),
            must_qty=Decimal("100"),
        )
        assert model.mto_number == "AK001"
        assert model.real_qty == Decimal("100")
        assert model.must_qty == Decimal("100")


class TestPurchaseOrderModel:
    """Tests for PurchaseOrderModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = PurchaseOrderModel(
            bill_no="PO001",
            mto_number="AK001",
            material_code="M001",
            order_qty=Decimal("100"),
            stock_in_qty=Decimal("80"),
            remain_stock_in_qty=Decimal("20"),
        )
        assert model.bill_no == "PO001"
        assert model.order_qty == Decimal("100")
        assert model.stock_in_qty == Decimal("80")
        assert model.remain_stock_in_qty == Decimal("20")

    def test_optional_fields(self):
        """Test optional fields default to empty string."""
        model = PurchaseOrderModel(
            bill_no="PO001",
            mto_number="AK001",
            material_code="M001",
            order_qty=Decimal("100"),
            stock_in_qty=Decimal("0"),
            remain_stock_in_qty=Decimal("100"),
        )
        assert model.material_name == ""
        assert model.specification == ""
        assert model.aux_attributes == ""
        assert model.aux_prop_id == 0


class TestPurchaseReceiptModel:
    """Tests for PurchaseReceiptModel."""

    def test_purchase_receipt(self):
        """Test purchase receipt (RKD01_SYS)."""
        model = PurchaseReceiptModel(
            mto_number="AK001",
            material_code="M001",
            real_qty=Decimal("100"),
            must_qty=Decimal("100"),
            bill_type_number="RKD01_SYS",
        )
        assert model.bill_type_number == "RKD01_SYS"

    def test_subcontracting_receipt(self):
        """Test subcontracting receipt (RKD02_SYS)."""
        model = PurchaseReceiptModel(
            mto_number="AK001",
            material_code="M001",
            real_qty=Decimal("50"),
            must_qty=Decimal("50"),
            bill_type_number="RKD02_SYS",
        )
        assert model.bill_type_number == "RKD02_SYS"


class TestSubcontractingOrderModel:
    """Tests for SubcontractingOrderModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = SubcontractingOrderModel(
            bill_no="SO001",
            mto_number="AK001",
            material_code="M001",
            order_qty=Decimal("50"),
            stock_in_qty=Decimal("25"),
            no_stock_in_qty=Decimal("25"),
        )
        assert model.bill_no == "SO001"
        assert model.order_qty == Decimal("50")
        assert model.stock_in_qty == Decimal("25")
        assert model.no_stock_in_qty == Decimal("25")


class TestMaterialPickingModel:
    """Tests for MaterialPickingModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = MaterialPickingModel(
            mto_number="AK001",
            material_code="M001",
            app_qty=Decimal("100"),
            actual_qty=Decimal("95"),
            ppbom_bill_no="PPBOM001",
        )
        assert model.mto_number == "AK001"
        assert model.app_qty == Decimal("100")
        assert model.actual_qty == Decimal("95")
        assert model.ppbom_bill_no == "PPBOM001"


class TestSalesDeliveryModel:
    """Tests for SalesDeliveryModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = SalesDeliveryModel(
            mto_number="AK001",
            material_code="M001",
            real_qty=Decimal("80"),
            must_qty=Decimal("100"),
        )
        assert model.mto_number == "AK001"
        assert model.real_qty == Decimal("80")
        assert model.must_qty == Decimal("100")


class TestSalesOrderModel:
    """Tests for SalesOrderModel."""

    def test_valid_model(self):
        """Test creating valid model."""
        model = SalesOrderModel(
            bill_no="SAL001",
            mto_number="AK001",
            material_code="07.02.037",
            customer_name="Customer A",
        )
        assert model.bill_no == "SAL001"
        assert model.mto_number == "AK001"
        assert model.material_code == "07.02.037"
        assert model.customer_name == "Customer A"
        assert model.delivery_date is None

    def test_with_delivery_date(self):
        """Test model with delivery date."""
        model = SalesOrderModel(
            bill_no="SAL001",
            mto_number="AK001",
            material_code="07.02.037",
            customer_name="Customer A",
            delivery_date="2025-02-01",
        )
        assert model.delivery_date == "2025-02-01"
