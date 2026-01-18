"""
Kingdee K3Cloud API Client Wrapper

Responsibilities:
1. Wrap K3Cloud SDK calls
2. Unified error handling and retry logic
3. Support async queries
4. Date range chunk queries
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Optional, TYPE_CHECKING

from k3cloud_webapi_sdk.main import K3CloudApiSdk

from src.exceptions import KingdeeQueryError

if TYPE_CHECKING:
    from src.config import KingdeeConfig

logger = logging.getLogger(__name__)


class KingdeeClient:
    """K3Cloud SDK Wrapper"""

    def __init__(self, config: "KingdeeConfig"):
        self.config = config
        self._sdk: Optional[K3CloudApiSdk] = None
        self._lock = asyncio.Lock()

    async def _get_sdk(self) -> K3CloudApiSdk:
        """Get or create SDK instance (thread-safe)."""
        async with self._lock:
            if self._sdk is None:
                self._sdk = K3CloudApiSdk(self.config.server_url)
                self._sdk.InitConfig(
                    acct_id=self.config.acct_id,
                    user_name=self.config.user_name,
                    app_id=self.config.app_id,
                    app_secret=self.config.app_sec,
                    server_url=self.config.server_url,
                    lcid=self.config.lcid,
                )
            return self._sdk

    async def query(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str = "",
        limit: int = 2000,
        start_row: int = 0,
    ) -> list[dict]:
        """
        Execute Query API call.

        Args:
            form_id: Form ID (e.g., PRD_MO, PRD_PPBOM)
            field_keys: Fields to return
            filter_string: Filter condition (SQL WHERE format)
            limit: Max records to return
            start_row: Starting row (for pagination)

        Returns:
            List of records, each record is a field-to-value dict

        Raises:
            KingdeeQueryError: When query fails
        """
        sdk = await self._get_sdk()

        params = {
            "FormId": form_id,
            "FieldKeys": ",".join(field_keys),
            "FilterString": filter_string,
            "Limit": limit,
            "StartRow": start_row,
        }

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: sdk.ExecuteBillQuery(params),
            )

            if not response:
                return []

            # SDK returns JSON string, need to parse it
            if isinstance(response, str):
                response = json.loads(response)

            # Handle SDK error responses (dict with 'Result' key)
            if isinstance(response, dict):
                result = response.get("Result", {})
                status = result.get("ResponseStatus", {})
                if not status.get("IsSuccess", True):
                    errors = status.get("Errors", [])
                    error_msg = "; ".join(e.get("Message", "") for e in errors) if errors else "Unknown error"
                    msg_code = result.get("MsgCode", 0)
                    # MsgCode 4 = form not found, return empty instead of error
                    if msg_code == 4 or "业务对象不存在" in error_msg:
                        logger.warning("Form %s not found or disabled: %s", form_id, error_msg)
                        return []
                    raise KingdeeQueryError(f"Query {form_id} failed: {error_msg}")
                # If successful but no data, return empty
                return []

            # Handle SDK error responses - can be wrapped in various ways:
            # 1. {'Result': {...}} - direct dict
            # 2. [{'Result': {...}}] - single wrapped
            # 3. [[{'Result': {...}}]] - double wrapped (common for errors)
            def extract_error(obj):
                """Extract error info if obj is an error response, else return None."""
                if isinstance(obj, dict) and "Result" in obj:
                    return obj.get("Result", {})
                if isinstance(obj, list) and len(obj) > 0:
                    return extract_error(obj[0])
                return None

            error_result = extract_error(response)
            if error_result:
                status = error_result.get("ResponseStatus", {})
                errors = status.get("Errors", [])
                error_msg = "; ".join(e.get("Message", "") for e in errors) if errors else "Unknown error"
                msg_code = error_result.get("MsgCode", 0)
                # MsgCode 4 = form not found, return empty instead of error
                if msg_code == 4 or "业务对象不存在" in error_msg or "字段不存在" in error_msg:
                    logger.warning("Form %s error (returning empty): %s", form_id, error_msg)
                    return []
                if not status.get("IsSuccess", True):
                    raise KingdeeQueryError(f"Query {form_id} failed: {error_msg}")
                # Unexpected success format
                return []

            # Filter out any non-list rows
            valid_rows = []
            for row in response:
                if isinstance(row, list):
                    # Check if this row itself is an error response
                    if len(row) > 0 and isinstance(row[0], dict) and "Result" in row[0]:
                        logger.warning("Skipping error row in response")
                        continue
                    valid_rows.append(dict(zip(field_keys, row)))

            return valid_rows

        except Exception as exc:
            logger.error("Kingdee query failed: %s, error: %s", form_id, exc)
            raise KingdeeQueryError(f"Query {form_id} failed: {exc}") from exc

    async def query_all(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str = "",
        page_size: int = 2000,
    ) -> list[dict]:
        """Paginated query for all records."""
        all_records: list[dict] = []
        start_row = 0

        while True:
            batch = await self.query(
                form_id=form_id,
                field_keys=field_keys,
                filter_string=filter_string,
                limit=page_size,
                start_row=start_row,
            )

            if not batch:
                break

            all_records.extend(batch)

            if len(batch) < page_size:
                break

            start_row += page_size

        logger.info("Query %s: %s records total", form_id, len(all_records))
        return all_records

    async def query_by_date_range(
        self,
        form_id: str,
        field_keys: list[str],
        date_field: str,
        start_date: date,
        end_date: date,
        extra_filter: str = "",
    ) -> list[dict]:
        """Query by date range."""
        filter_parts = [
            f"{date_field}>='{start_date.isoformat()}'",
            f"{date_field}<='{end_date.isoformat()}'",
        ]

        if extra_filter:
            filter_parts.append(f"({extra_filter})")

        filter_string = " AND ".join(filter_parts)

        return await self.query_all(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string,
        )

    async def query_by_mto(
        self,
        form_id: str,
        field_keys: list[str],
        mto_field: str,
        mto_number: str,
    ) -> list[dict]:
        """Query by MTO number."""
        filter_string = f"{mto_field}='{mto_number}'"
        return await self.query_all(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string,
        )

    async def lookup_aux_properties(self, aux_prop_ids: list[int]) -> dict[int, str]:
        """
        Lookup auxiliary property descriptions from BD_FLEXSITEMDETAILV.

        Args:
            aux_prop_ids: List of FAuxPropId values to look up

        Returns:
            Dict mapping aux_prop_id to description string.
            For purchased items: FF100001 (specification description)
            For self-made items: FF100002.FName (color name)
        """
        if not aux_prop_ids:
            return {}

        # Filter out zeros and duplicates
        valid_ids = list(set(id for id in aux_prop_ids if id and id > 0))
        if not valid_ids:
            return {}

        # Build IN clause for batch query
        in_clause = ",".join(str(id) for id in valid_ids)
        filter_string = f"FID IN ({in_clause})"

        # Query both FF100001 (spec) and FF100002.FName (color)
        records = await self.query_all(
            form_id="BD_FLEXSITEMDETAILV",
            field_keys=["FID", "FF100001", "FF100002.FName"],
            filter_string=filter_string,
        )

        result: dict[int, str] = {}
        for record in records:
            fid = record.get("FID")
            if not fid:
                continue

            # Prefer FF100001 (spec description) if non-empty
            # Otherwise use FF100002.FName (color name)
            spec = record.get("FF100001", "")
            color = record.get("FF100002.FName", "")

            description = ""
            if spec and str(spec).strip():
                description = str(spec).strip()
            elif color and str(color).strip():
                description = str(color).strip()

            if description:
                result[int(fid)] = description

        logger.info("Looked up %d aux properties, found %d descriptions", len(valid_ids), len(result))
        return result
