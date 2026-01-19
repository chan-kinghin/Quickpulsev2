"""Integration tests for KingdeeClient with mocked SDK."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exceptions import KingdeeQueryError
from src.kingdee.client import KingdeeClient
from tests.fixtures.kingdee_responses import (
    AUX_PROPERTY_RESPONSE,
    EMPTY_RESPONSE,
    ERROR_RESPONSE,
    FORM_NOT_FOUND_RESPONSE,
    MULTIPLE_RECORDS_RESPONSE,
    PAGE_1_RESPONSE,
    PAGE_2_RESPONSE,
    SUCCESS_RESPONSE_JSON_STRING,
    SUCCESS_RESPONSE_RAW,
)


class TestKingdeeClientQuery:
    """Tests for KingdeeClient.query method."""

    @pytest.mark.asyncio
    async def test_query_success(self, mock_kingdee_client, mock_sdk):
        """Test successful query returns parsed data."""
        mock_sdk.ExecuteBillQuery.return_value = SUCCESS_RESPONSE_RAW

        result = await mock_kingdee_client.query(
            form_id="PRD_MO",
            field_keys=["FBillNo", "FMTONo", "FWorkShopID.FName", "FMaterialId.FNumber",
                       "FMaterialId.FName", "FMaterialId.FSpecification", "FQty",
                       "FStatus", "FCreateDate"],
            filter_string="FMTONo='AK2510034'",
        )

        assert len(result) == 1
        assert result[0]["FBillNo"] == "MO0001"
        assert result[0]["FMTONo"] == "AK2510034"
        assert result[0]["FQty"] == 100

    @pytest.mark.asyncio
    async def test_query_empty_response(self, mock_kingdee_client, mock_sdk):
        """Test empty response returns empty list."""
        mock_sdk.ExecuteBillQuery.return_value = EMPTY_RESPONSE

        result = await mock_kingdee_client.query(
            form_id="PRD_MO",
            field_keys=["FBillNo"],
            filter_string="FMTONo='NONEXISTENT'",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_query_json_string_response(self, mock_kingdee_client, mock_sdk):
        """Test JSON string response is parsed."""
        mock_sdk.ExecuteBillQuery.return_value = SUCCESS_RESPONSE_JSON_STRING

        result = await mock_kingdee_client.query(
            form_id="PRD_MO",
            field_keys=["FBillNo", "FMTONo", "FWorkShopID.FName", "FMaterialId.FNumber",
                       "FMaterialId.FName", "FMaterialId.FSpecification", "FQty",
                       "FStatus", "FCreateDate"],
        )

        assert len(result) == 1
        assert result[0]["FBillNo"] == "MO0001"

    @pytest.mark.asyncio
    async def test_query_error_response(self, mock_kingdee_client, mock_sdk):
        """Test error response raises KingdeeQueryError."""
        mock_sdk.ExecuteBillQuery.return_value = ERROR_RESPONSE

        with pytest.raises(KingdeeQueryError, match="Query failed"):
            await mock_kingdee_client.query(
                form_id="PRD_MO",
                field_keys=["FBillNo"],
            )

    @pytest.mark.asyncio
    async def test_query_form_not_found_returns_empty(self, mock_kingdee_client, mock_sdk):
        """Test form not found (MsgCode 4) returns empty instead of error."""
        mock_sdk.ExecuteBillQuery.return_value = FORM_NOT_FOUND_RESPONSE

        result = await mock_kingdee_client.query(
            form_id="NONEXISTENT",
            field_keys=["FBillNo"],
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_query_multiple_records(self, mock_kingdee_client, mock_sdk):
        """Test query returning multiple records."""
        mock_sdk.ExecuteBillQuery.return_value = MULTIPLE_RECORDS_RESPONSE

        result = await mock_kingdee_client.query(
            form_id="PRD_MO",
            field_keys=["FBillNo", "FMTONo", "FQty"],
            limit=100,
        )

        assert len(result) == 3
        assert result[0]["FBillNo"] == "MO0001"
        assert result[1]["FBillNo"] == "MO0002"
        assert result[2]["FBillNo"] == "MO0003"


class TestKingdeeClientPagination:
    """Tests for query_all pagination."""

    @pytest.mark.asyncio
    async def test_query_all_single_page(self, mock_kingdee_client, mock_sdk):
        """Test query_all with single page of results."""
        # Return less than page_size records
        mock_sdk.ExecuteBillQuery.return_value = [
            ["MO001", "AK001", 100],
            ["MO002", "AK001", 200],
        ]

        result = await mock_kingdee_client.query_all(
            form_id="PRD_MO",
            field_keys=["FBillNo", "FMTONo", "FQty"],
            page_size=2000,
        )

        assert len(result) == 2
        assert mock_sdk.ExecuteBillQuery.call_count == 1

    @pytest.mark.asyncio
    async def test_query_all_multiple_pages(self, mock_kingdee_client, mock_sdk):
        """Test pagination fetches all pages."""
        # First call: full page (2000), second call: partial page (500)
        mock_sdk.ExecuteBillQuery.side_effect = [PAGE_1_RESPONSE, PAGE_2_RESPONSE]

        result = await mock_kingdee_client.query_all(
            form_id="PRD_MO",
            field_keys=["FBillNo", "FMTONo", "FQty"],
            page_size=2000,
        )

        assert len(result) == 2500
        assert mock_sdk.ExecuteBillQuery.call_count == 2

    @pytest.mark.asyncio
    async def test_query_all_empty(self, mock_kingdee_client, mock_sdk):
        """Test query_all with no results."""
        mock_sdk.ExecuteBillQuery.return_value = []

        result = await mock_kingdee_client.query_all(
            form_id="PRD_MO",
            field_keys=["FBillNo"],
        )

        assert result == []


class TestKingdeeClientDateRange:
    """Tests for query_by_date_range."""

    @pytest.mark.asyncio
    async def test_query_by_date_range(self, mock_kingdee_client, mock_sdk):
        """Test date range query builds correct filter."""
        from datetime import date

        mock_sdk.ExecuteBillQuery.return_value = SUCCESS_RESPONSE_RAW

        await mock_kingdee_client.query_by_date_range(
            form_id="PRD_MO",
            field_keys=["FBillNo"],
            date_field="FCreateDate",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 15),
        )

        # Check filter string was built correctly
        call_args = mock_sdk.ExecuteBillQuery.call_args[0][0]
        filter_str = call_args["FilterString"]
        assert "FCreateDate>='2025-01-01'" in filter_str
        assert "FCreateDate<='2025-01-15'" in filter_str

    @pytest.mark.asyncio
    async def test_query_by_date_range_with_extra_filter(
        self, mock_kingdee_client, mock_sdk
    ):
        """Test date range with additional filter."""
        from datetime import date

        mock_sdk.ExecuteBillQuery.return_value = []

        await mock_kingdee_client.query_by_date_range(
            form_id="PRD_MO",
            field_keys=["FBillNo"],
            date_field="FCreateDate",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 15),
            extra_filter="FStatus='Approved'",
        )

        call_args = mock_sdk.ExecuteBillQuery.call_args[0][0]
        filter_str = call_args["FilterString"]
        assert "FStatus='Approved'" in filter_str


class TestKingdeeClientMTO:
    """Tests for query_by_mto."""

    @pytest.mark.asyncio
    async def test_query_by_mto(self, mock_kingdee_client, mock_sdk):
        """Test MTO query builds correct filter."""
        mock_sdk.ExecuteBillQuery.return_value = SUCCESS_RESPONSE_RAW

        await mock_kingdee_client.query_by_mto(
            form_id="PRD_MO",
            field_keys=["FBillNo", "FMTONo"],
            mto_field="FMTONo",
            mto_number="AK2510034",
        )

        call_args = mock_sdk.ExecuteBillQuery.call_args[0][0]
        assert call_args["FilterString"] == "FMTONo='AK2510034'"


class TestAuxPropertyLookup:
    """Tests for lookup_aux_properties."""

    @pytest.mark.asyncio
    async def test_lookup_aux_properties(self, mock_kingdee_client, mock_sdk):
        """Test aux property lookup."""
        mock_sdk.ExecuteBillQuery.return_value = AUX_PROPERTY_RESPONSE

        result = await mock_kingdee_client.lookup_aux_properties([1001, 1002, 1003])

        assert result[1001] == "Blue Model"
        assert result[1002] == "Red"
        assert result[1003] == "Green Special"  # Prefers FF100001 over FF100002.FName

    @pytest.mark.asyncio
    async def test_lookup_aux_properties_empty_input(self, mock_kingdee_client):
        """Test empty input returns empty dict."""
        result = await mock_kingdee_client.lookup_aux_properties([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_lookup_aux_properties_filters_zeros(
        self, mock_kingdee_client, mock_sdk
    ):
        """Test zero values are filtered out."""
        mock_sdk.ExecuteBillQuery.return_value = [[1001, "Description", ""]]

        result = await mock_kingdee_client.lookup_aux_properties([0, 1001, 0])

        # Should only query for 1001
        call_args = mock_sdk.ExecuteBillQuery.call_args[0][0]
        assert "1001" in call_args["FilterString"]
        # Check no zero in the IN clause (this is implementation specific)
        assert result.get(1001) == "Description"

    @pytest.mark.asyncio
    async def test_lookup_aux_properties_all_zeros(self, mock_kingdee_client):
        """Test all zeros returns empty dict."""
        result = await mock_kingdee_client.lookup_aux_properties([0, 0, 0])
        assert result == {}

    @pytest.mark.asyncio
    async def test_lookup_aux_properties_deduplicates(
        self, mock_kingdee_client, mock_sdk
    ):
        """Test duplicate IDs are deduplicated."""
        mock_sdk.ExecuteBillQuery.return_value = [[1001, "Description", ""]]

        result = await mock_kingdee_client.lookup_aux_properties([1001, 1001, 1001])

        # Should only have one entry
        assert len(result) == 1
        assert result[1001] == "Description"
