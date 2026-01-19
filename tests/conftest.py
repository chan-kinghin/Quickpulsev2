"""Shared fixtures for QuickPulse V2 tests."""

import asyncio
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# ============================================================================
# Event Loop Fixture
# ============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def temp_db_path() -> AsyncGenerator[Path, None]:
    """Create temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest_asyncio.fixture
async def test_database(temp_db_path: Path):
    """Initialized test database."""
    from src.database.connection import Database

    db = Database(temp_db_path)
    await db.connect()
    yield db
    await db.close()


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def mock_kingdee_config():
    """Mock KingdeeConfig for testing."""
    from src.config import KingdeeConfig

    return KingdeeConfig(
        server_url="http://test.kingdee.com/k3cloud/",
        acct_id="test_acct",
        user_name="test_user",
        app_id="test_app",
        app_sec="test_secret",
        lcid=2052,
        connect_timeout=15,
        request_timeout=30,
    )


@pytest.fixture
def mock_sync_config():
    """Default SyncConfig for testing."""
    from src.config import SyncConfig

    return SyncConfig()


@pytest.fixture
def test_config(mock_kingdee_config, mock_sync_config, temp_db_path):
    """Complete test Config."""
    from src.config import Config

    return Config(
        kingdee=mock_kingdee_config,
        sync=mock_sync_config,
        db_path=temp_db_path,
        reports_dir=temp_db_path.parent / "reports",
    )


# ============================================================================
# Kingdee Client Mocking
# ============================================================================


@pytest.fixture
def mock_sdk():
    """Mock K3CloudApiSdk."""
    sdk = MagicMock()
    sdk.InitConfig = MagicMock()
    sdk.ExecuteBillQuery = MagicMock(return_value=[])
    return sdk


@pytest.fixture
def mock_kingdee_client(mock_kingdee_config, mock_sdk):
    """KingdeeClient with mocked SDK."""
    from src.kingdee.client import KingdeeClient

    client = KingdeeClient(mock_kingdee_config)
    client._sdk = mock_sdk
    return client


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_production_order():
    """Sample ProductionOrderModel."""
    from src.readers.models import ProductionOrderModel

    return ProductionOrderModel(
        bill_no="MO0001",
        mto_number="AK2510034",
        workshop="Workshop A",
        material_code="M001",
        material_name="Test Material",
        specification="Spec A",
        qty=Decimal("100"),
        status="Approved",
        create_date="2025-01-15",
    )


@pytest.fixture
def sample_production_orders():
    """Multiple sample ProductionOrderModels."""
    from src.readers.models import ProductionOrderModel

    return [
        ProductionOrderModel(
            bill_no="MO0001",
            mto_number="AK2510034",
            workshop="Workshop A",
            material_code="P001",
            material_name="Finished Product A",
            specification="Spec A",
            qty=Decimal("100"),
            status="Approved",
            create_date="2025-01-15",
        ),
        ProductionOrderModel(
            bill_no="MO0002",
            mto_number="AK2510034",
            workshop="Workshop B",
            material_code="P002",
            material_name="Finished Product B",
            specification="Spec B",
            qty=Decimal("50"),
            status="Approved",
            create_date="2025-01-16",
        ),
    ]


@pytest.fixture
def sample_bom_entries():
    """Sample ProductionBOMModel list covering all material types."""
    from src.readers.models import ProductionBOMModel

    return [
        # Self-made (material_type=1)
        ProductionBOMModel(
            mo_bill_no="MO0001",
            mto_number="AK2510034",
            material_code="C001",
            material_name="Self-made Part 1",
            specification="Spec1",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("50"),
            picked_qty=Decimal("30"),
            no_picked_qty=Decimal("20"),
        ),
        # Purchased (material_type=2)
        ProductionBOMModel(
            mo_bill_no="MO0001",
            mto_number="AK2510034",
            material_code="C002",
            material_name="Purchased Part 1",
            specification="Spec2",
            aux_attributes="Blue",
            aux_prop_id=1001,
            material_type=2,
            need_qty=Decimal("100"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("100"),
        ),
        # Subcontracted (material_type=3)
        ProductionBOMModel(
            mo_bill_no="MO0001",
            mto_number="AK2510034",
            material_code="C003",
            material_name="Subcontracted Part 1",
            specification="Spec3",
            aux_attributes="",
            aux_prop_id=0,
            material_type=3,
            need_qty=Decimal("25"),
            picked_qty=Decimal("25"),
            no_picked_qty=Decimal("0"),
        ),
    ]


@pytest.fixture
def sample_production_receipts():
    """Sample ProductionReceiptModel list."""
    from src.readers.models import ProductionReceiptModel

    return [
        ProductionReceiptModel(
            mto_number="AK2510034",
            material_code="C001",
            real_qty=Decimal("20"),
            must_qty=Decimal("50"),
        ),
    ]


@pytest.fixture
def sample_purchase_receipts():
    """Sample PurchaseReceiptModel list."""
    from src.readers.models import PurchaseReceiptModel

    return [
        # Purchase receipt (RKD01_SYS)
        PurchaseReceiptModel(
            mto_number="AK2510034",
            material_code="C002",
            real_qty=Decimal("80"),
            must_qty=Decimal("100"),
            bill_type_number="RKD01_SYS",
        ),
        # Subcontracting receipt (RKD02_SYS)
        PurchaseReceiptModel(
            mto_number="AK2510034",
            material_code="C003",
            real_qty=Decimal("25"),
            must_qty=Decimal("25"),
            bill_type_number="RKD02_SYS",
        ),
    ]


@pytest.fixture
def sample_purchase_orders():
    """Sample PurchaseOrderModel list."""
    from src.readers.models import PurchaseOrderModel

    return [
        PurchaseOrderModel(
            bill_no="PO0001",
            mto_number="AK2510034",
            material_code="C002",
            material_name="Purchased Part 1",
            specification="Spec2",
            aux_attributes="Blue",
            aux_prop_id=1001,
            order_qty=Decimal("100"),
            stock_in_qty=Decimal("80"),
            remain_stock_in_qty=Decimal("20"),
        ),
    ]


@pytest.fixture
def sample_subcontracting_orders():
    """Sample SubcontractingOrderModel list."""
    from src.readers.models import SubcontractingOrderModel

    return [
        SubcontractingOrderModel(
            bill_no="SO0001",
            mto_number="AK2510034",
            material_code="C003",
            order_qty=Decimal("25"),
            stock_in_qty=Decimal("25"),
            no_stock_in_qty=Decimal("0"),
        ),
    ]


@pytest.fixture
def sample_mto_response():
    """Sample MTOStatusResponse for API tests."""
    from datetime import datetime

    from src.models.mto_status import ChildItem, MTOStatusResponse, ParentItem

    return MTOStatusResponse(
        mto_number="AK2510034",
        parent=ParentItem(
            mto_number="AK2510034",
            customer_name="Test Customer",
            delivery_date="2025-02-01",
        ),
        children=[
            ChildItem(
                material_code="C001",
                material_name="Component 1",
                specification="Spec C1",
                aux_attributes="",
                material_type=1,
                material_type_name="Self-made",
                required_qty=Decimal("50"),
                picked_qty=Decimal("30"),
                unpicked_qty=Decimal("20"),
                order_qty=Decimal("50"),
                receipt_qty=Decimal("25"),
                unreceived_qty=Decimal("25"),
                pick_request_qty=Decimal("50"),
                pick_actual_qty=Decimal("30"),
                delivered_qty=Decimal("10"),
                inventory_qty=Decimal("15"),
                receipt_source="PRD_INSTOCK",
            ),
        ],
        query_time=datetime(2025, 1, 15, 10, 0),
        data_source="live",
    )


# ============================================================================
# Reader Fixtures
# ============================================================================


@pytest.fixture
def mock_readers(mock_kingdee_client):
    """Dictionary of mock readers with AsyncMock methods."""
    from src.readers import (
        MaterialPickingReader,
        ProductionBOMReader,
        ProductionOrderReader,
        ProductionReceiptReader,
        PurchaseOrderReader,
        PurchaseReceiptReader,
        SalesDeliveryReader,
        SalesOrderReader,
        SubcontractingOrderReader,
    )

    readers = {
        "production_order": ProductionOrderReader(mock_kingdee_client),
        "production_bom": ProductionBOMReader(mock_kingdee_client),
        "production_receipt": ProductionReceiptReader(mock_kingdee_client),
        "purchase_order": PurchaseOrderReader(mock_kingdee_client),
        "purchase_receipt": PurchaseReceiptReader(mock_kingdee_client),
        "subcontracting_order": SubcontractingOrderReader(mock_kingdee_client),
        "material_picking": MaterialPickingReader(mock_kingdee_client),
        "sales_delivery": SalesDeliveryReader(mock_kingdee_client),
        "sales_order": SalesOrderReader(mock_kingdee_client),
    }

    # Mock all async methods
    for reader in readers.values():
        reader.fetch_by_mto = AsyncMock(return_value=[])
        reader.fetch_by_bill_nos = AsyncMock(return_value=[])
        reader.fetch_by_date_range = AsyncMock(return_value=[])

    return readers


# ============================================================================
# Sync Fixtures
# ============================================================================


@pytest.fixture
def temp_reports_dir():
    """Temporary reports directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_sync_progress(temp_reports_dir):
    """SyncProgress with temporary file."""
    from src.sync.progress import SyncProgress

    return SyncProgress(temp_reports_dir / "sync_status.json")


# ============================================================================
# Response Fixtures
# ============================================================================


@pytest.fixture
def sample_mto_response():
    """Sample MTOStatusResponse."""
    from src.models.mto_status import ChildItem, MTOStatusResponse, ParentItem

    return MTOStatusResponse(
        mto_number="AK2510034",
        parent=ParentItem(
            mto_number="AK2510034",
            customer_name="Customer A",
            delivery_date="2025-02-01",
        ),
        children=[
            ChildItem(
                material_code="C001",
                material_name="Self-made Part 1",
                specification="Spec1",
                aux_attributes="",
                material_type=1,
                material_type_name="Self-made",
                required_qty=Decimal("50"),
                picked_qty=Decimal("30"),
                unpicked_qty=Decimal("20"),
                order_qty=Decimal("50"),
                receipt_qty=Decimal("20"),
                unreceived_qty=Decimal("30"),
                pick_request_qty=Decimal("0"),
                pick_actual_qty=Decimal("0"),
                delivered_qty=Decimal("0"),
                inventory_qty=Decimal("0"),
                receipt_source="PRD_INSTOCK",
            ),
        ],
        query_time=datetime.now(),
        data_source="live",
    )
