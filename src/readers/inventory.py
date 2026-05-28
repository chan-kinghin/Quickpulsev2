"""Inventory search reader — material → warehouse breakdown via Kingdee STK_Inventory."""

import asyncio
import re
from decimal import Decimal

from src.kingdee.client import KingdeeClient
from src.models.inventory import (
    ERP_CLASS_LABELS,
    InventoryDetail,
    InventorySearchResponse,
    MaterialMatch,
    WarehouseRow,
)

# Whitelist: CJK + ASCII alnum + dot + dash + underscore + space, length 2-50
_QUERY_RE = re.compile(r"^[\w\s一-鿿\.\-]{2,50}$")

_BD_MATERIAL_FIELDS = ["FNumber", "FName", "FSpecification", "FErpClsID"]
_STK_INVENTORY_FIELDS = [
    "FMaterialId.FNumber",
    "FStockId.FNumber",
    "FStockId.FName",
    "FAuxPropId",
    "FLot.FNumber",
    "FBaseQty",
    "FStockOrgId.FName",
]
_AUX_FIELDS = ["FID", "FF100001", "FF100002.FName"]

_AUX_BATCH_SIZE = 200
_SEARCH_SERVER_CAP = 50


def sanitize_query(q: str) -> str:
    """Validate user query before injecting into Kingdee FilterString.

    Raises ValueError if invalid. Returns SQL-escaped string (single quotes doubled)
    even though regex already blocks them — defense in depth.
    """
    q = q.strip()
    if not _QUERY_RE.match(q):
        raise ValueError("Invalid characters in query")
    return q.replace("'", "''")


class InventoryReader:
    def __init__(self, client: KingdeeClient):
        self.client = client

    async def search_materials(self, q: str, limit: int = 20) -> InventorySearchResponse:
        """Search materials by code / name / spec, with aux-attribute discovery.

        Two parallel paths:
        1. BD_MATERIAL fuzzy on FNumber / FName / FSpecification (FForbidStatus='A')
        2. BD_FLEXSITEMDETAILV fuzzy on FF100001 / FF100002.FName → reverse-lookup
           materials that have non-zero STK_Inventory rows under those aux IDs.
        Results are merged, deduped by material_code, capped at server limit.
        """
        safe_q = sanitize_query(q)
        server_limit = min(limit, _SEARCH_SERVER_CAP)

        material_filter = (
            f"(FNumber like '%{safe_q}%' or FName like '%{safe_q}%' "
            f"or FSpecification like '%{safe_q}%') and FForbidStatus = 'A'"
        )
        aux_filter = f"FF100001 like '%{safe_q}%' or FF100002.FName like '%{safe_q}%'"

        bd_rows, aux_rows = await asyncio.gather(
            self.client.query(
                form_id="BD_MATERIAL",
                field_keys=_BD_MATERIAL_FIELDS,
                filter_string=material_filter,
                limit=server_limit,
            ),
            self.client.query(
                form_id="BD_FLEXSITEMDETAILV",
                field_keys=_AUX_FIELDS,
                filter_string=aux_filter,
                limit=_AUX_BATCH_SIZE,
            ),
        )

        seen: set[str] = set()
        items: list[MaterialMatch] = []
        for r in bd_rows:
            match = _row_to_material_match(r)
            if match.material_code in seen:
                continue
            seen.add(match.material_code)
            items.append(match)

        if aux_rows and len(items) < server_limit:
            aux_ids = [str(int(r["FID"])) for r in aux_rows if r.get("FID")]
            extra_codes = await self._materials_with_aux(aux_ids, exclude=seen, limit=server_limit - len(items))
            if extra_codes:
                extras = await self._fetch_materials_by_codes(extra_codes)
                for r in extras:
                    match = _row_to_material_match(r)
                    if match.material_code in seen:
                        continue
                    seen.add(match.material_code)
                    items.append(match)
                    if len(items) >= server_limit:
                        break

        return InventorySearchResponse(query=q, total=len(items), items=items)

    async def _materials_with_aux(
        self, aux_ids: list[str], exclude: set[str], limit: int,
    ) -> list[str]:
        """Find material codes that have non-zero inventory under any of these aux_ids."""
        if not aux_ids:
            return []
        in_clause = ",".join(aux_ids)
        rows = await self.client.query(
            form_id="STK_Inventory",
            field_keys=["FMaterialId.FNumber"],
            filter_string=f"FAuxPropId IN ({in_clause}) and FBaseQty <> 0",
            limit=500,
        )
        codes: list[str] = []
        seen_extra: set[str] = set()
        for r in rows:
            code = r.get("FMaterialId.FNumber")
            if not code or code in exclude or code in seen_extra:
                continue
            seen_extra.add(code)
            codes.append(code)
            if len(codes) >= limit:
                break
        return codes

    async def _fetch_materials_by_codes(self, codes: list[str]) -> list[dict]:
        """Fetch BD_MATERIAL metadata for a list of codes via IN clause."""
        if not codes:
            return []
        in_clause = ",".join(f"'{c}'" for c in codes)
        return await self.client.query(
            form_id="BD_MATERIAL",
            field_keys=_BD_MATERIAL_FIELDS,
            filter_string=f"FNumber IN ({in_clause}) and FForbidStatus = 'A'",
            limit=len(codes),
        )

    async def get_inventory_by_material(
        self,
        material_code: str,
        include_zero: bool = False,
    ) -> InventoryDetail:
        """Step B + C: query STK_Inventory for one material, resolve aux IDs.

        1. Hit BD_MATERIAL once to get name/spec/erp_class.
        2. Hit STK_Inventory filtered by FMaterialId.FNumber.
        3. Collect all non-zero aux_ids, batch-resolve via BD_FLEXSITEMDETAILV.
        4. Sort rows by base_qty desc.
        5. Compute total_qty and warehouse_count.
        """
        # Step 1: fetch material metadata
        mat_rows = await self.client.query(
            form_id="BD_MATERIAL",
            field_keys=_BD_MATERIAL_FIELDS,
            filter_string=f"FNumber = '{material_code}'",
            limit=1,
        )

        if not mat_rows:
            return InventoryDetail(
                material_code=material_code,
                material_name="",
                specification="",
                erp_class="",
                erp_class_label="",
                total_qty=Decimal(0),
                warehouse_count=0,
                rows=[],
            )

        mat = mat_rows[0]
        erp_class = str(mat.get("FErpClsID", "") or "")

        # Step 2: fetch inventory rows
        inv_filter = f"FMaterialId.FNumber = '{material_code}'"
        if not include_zero:
            inv_filter += " and FBaseQty <> 0"

        inv_rows = await self.client.query_all(
            form_id="STK_Inventory",
            field_keys=_STK_INVENTORY_FIELDS,
            filter_string=inv_filter,
        )

        # Step 3: collect aux_ids for batch resolution
        aux_ids: set[int] = set()
        for r in inv_rows:
            raw = r.get("FAuxPropId")
            if raw:
                try:
                    aid = int(raw)
                    if aid > 0:
                        aux_ids.add(aid)
                except (ValueError, TypeError):
                    pass

        aux_map = await self._resolve_aux_descriptions(aux_ids)

        # Step 4: build WarehouseRow list and sort
        warehouse_rows = [_row_to_warehouse_row(r, aux_map) for r in inv_rows]
        warehouse_rows.sort(key=lambda x: x.base_qty, reverse=True)

        # Step 5: compute aggregates
        total_qty = sum((wr.base_qty for wr in warehouse_rows), Decimal(0))
        warehouse_count = len({wr.warehouse_code for wr in warehouse_rows})

        return InventoryDetail(
            material_code=material_code,
            material_name=str(mat.get("FName", "") or ""),
            specification=str(mat.get("FSpecification", "") or ""),
            erp_class=erp_class,
            erp_class_label=ERP_CLASS_LABELS.get(erp_class, ""),
            total_qty=total_qty,
            warehouse_count=warehouse_count,
            rows=warehouse_rows,
        )

    async def _resolve_aux_descriptions(self, aux_ids: set[int]) -> dict[int, str]:
        """Batch-query BD_FLEXSITEMDETAILV in chunks of 200.

        Skip aux_id=0. Returns {aux_id: description}.
        Description: FF100001 (spec) with fallback to FF100002.FName (color).
        """
        if not aux_ids:
            return {}

        valid_ids = [aid for aid in aux_ids if aid > 0]
        if not valid_ids:
            return {}

        result: dict[int, str] = {}
        for i in range(0, len(valid_ids), _AUX_BATCH_SIZE):
            batch = valid_ids[i : i + _AUX_BATCH_SIZE]
            in_clause = ",".join(str(x) for x in batch)
            rows = await self.client.query(
                form_id="BD_FLEXSITEMDETAILV",
                field_keys=_AUX_FIELDS,
                filter_string=f"FID IN ({in_clause})",
                limit=_AUX_BATCH_SIZE,
            )
            for r in rows:
                fid_raw = r.get("FID")
                if not fid_raw:
                    continue
                spec = str(r.get("FF100001", "") or "").strip()
                color = str(r.get("FF100002.FName", "") or "").strip()
                desc = spec or color
                result[int(fid_raw)] = desc

        return result


def _row_to_material_match(row: dict) -> MaterialMatch:
    """Convert a BD_MATERIAL dict row to MaterialMatch."""
    erp_class = str(row.get("FErpClsID", "") or "")
    return MaterialMatch(
        material_code=str(row.get("FNumber", "") or ""),
        material_name=str(row.get("FName", "") or ""),
        specification=str(row.get("FSpecification", "") or ""),
        erp_class=erp_class,
        erp_class_label=ERP_CLASS_LABELS.get(erp_class, ""),
    )


def _row_to_warehouse_row(row: dict, aux_map: dict[int, str]) -> WarehouseRow:
    """Convert a STK_Inventory dict row to WarehouseRow."""
    raw_aux = row.get("FAuxPropId")
    try:
        aux_id = int(raw_aux) if raw_aux else 0
    except (ValueError, TypeError):
        aux_id = 0

    raw_qty = row.get("FBaseQty")
    try:
        base_qty = Decimal(str(raw_qty)) if raw_qty is not None else Decimal(0)
    except Exception:
        base_qty = Decimal(0)

    aux_desc = aux_map.get(aux_id, "") if aux_id > 0 else ""

    return WarehouseRow(
        warehouse_code=str(row.get("FStockId.FNumber", "") or ""),
        warehouse_name=str(row.get("FStockId.FName", "") or ""),
        lot_number=str(row.get("FLot.FNumber", "") or ""),
        aux_id=aux_id,
        aux_desc=aux_desc,
        base_qty=base_qty,
        stock_org=str(row.get("FStockOrgId.FName", "") or ""),
    )
