"""Inventory search reader — material → warehouse breakdown via Kingdee STK_Inventory."""

import asyncio
import re
from decimal import Decimal
from typing import Optional

from src.kingdee.client import KingdeeClient
from src.models.inventory import (
    ERP_CLASS_LABELS,
    InventoryDetail,
    InventorySearchResponse,
    MaterialMatch,
    WarehouseRow,
)

# Whitelist per-token: CJK + ASCII alnum + dot + dash + underscore, length 2-50
# Note: spaces are stripped before per-token validation; individual tokens must not contain spaces.
_QUERY_RE = re.compile(r"^[\w一-鿿\.\-]{2,50}$")

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
_MAX_TOKENS = 4

# Valid erp_class codes accepted by the filter
_VALID_ERP_CLASSES = {"1", "2", "3", "4", "9"}


def sanitize_query(q: str) -> str:
    """Validate a single query token before injecting into Kingdee FilterString.

    Raises ValueError if invalid. Returns SQL-escaped string (single quotes doubled)
    even though regex already blocks them — defense in depth.
    """
    q = q.strip()
    if not _QUERY_RE.match(q):
        raise ValueError("Invalid characters in query")
    return q.replace("'", "''")


def tokenize(q: str) -> list[str]:
    """Split query on ASCII space and CJK fullwidth space (\\u3000).

    Each resulting token is individually validated by sanitize_query().
    Empty parts are dropped. Raises ValueError if more than _MAX_TOKENS tokens
    are produced, or if any token fails sanitize_query().
    """
    raw_tokens = re.split(r"[\s　]+", q.strip())
    tokens = [t for t in raw_tokens if t]  # drop empties
    if len(tokens) > _MAX_TOKENS:
        raise ValueError(
            f"Too many search tokens ({len(tokens)}); maximum is {_MAX_TOKENS}"
        )
    return [sanitize_query(t) for t in tokens]


class InventoryReader:
    def __init__(self, client: KingdeeClient):
        self.client = client

    async def search_materials(
        self,
        q: str,
        limit: int = 20,
        erp_classes: Optional[list[str]] = None,
    ) -> InventorySearchResponse:
        """Multi-token AND search with optional erp_class filter.

        Splits the query on whitespace into up to _MAX_TOKENS tokens. For each
        token a candidate material_code set is computed via:
          - BD_MATERIAL path: FNumber/FName/FSpecification LIKE %token%
          - aux path: BD_FLEXSITEMDETAILV FF100001/FF100002.FName LIKE %token%
            → aux_ids → STK_Inventory FAuxPropId IN (...) → material codes

        The final result is the intersection of all per-token candidate sets.
        For a single-token query this is equivalent to the original single-token
        behavior (union of material + aux paths, no intersection shrinkage).
        """
        tokens = tokenize(q)
        server_limit = min(limit, _SEARCH_SERVER_CAP)

        erp_clause = ""
        if erp_classes:
            bad = [c for c in erp_classes if c not in _VALID_ERP_CLASSES]
            if bad:
                raise ValueError(f"Invalid erp_class values: {bad}")
            in_list = ",".join(f"'{c}'" for c in erp_classes)
            erp_clause = f" and FErpClsID IN ({in_list})"

        # Per-token candidate sets computed in parallel
        candidate_sets = await asyncio.gather(
            *[self._candidates_for_token(t, erp_clause) for t in tokens]
        )

        final_codes: set[str] = set.intersection(*candidate_sets) if candidate_sets else set()
        final_codes_list = sorted(final_codes)[:server_limit]

        if not final_codes_list:
            return InventorySearchResponse(query=q, total=0, items=[])

        rows = await self._fetch_materials_by_codes(final_codes_list, erp_clause=erp_clause)
        items: list[MaterialMatch] = []
        seen: set[str] = set()
        for r in rows:
            m = _row_to_material_match(r)
            if m.material_code in seen:
                continue
            seen.add(m.material_code)
            items.append(m)

        return InventorySearchResponse(query=q, total=len(items), items=items)

    async def _candidates_for_token(self, token: str, erp_clause: str) -> set[str]:
        """Return set of material_codes matching this single token (BD_MATERIAL union aux path)."""
        material_filter = (
            f"(FNumber like '%{token}%' or FName like '%{token}%' "
            f"or FSpecification like '%{token}%') and FForbidStatus = 'A'"
            f"{erp_clause}"
        )
        aux_filter = f"FF100001 like '%{token}%' or FF100002.FName like '%{token}%'"

        bd_rows, aux_rows = await asyncio.gather(
            self.client.query(
                form_id="BD_MATERIAL",
                field_keys=["FNumber"],
                filter_string=material_filter,
                limit=500,
            ),
            self.client.query(
                form_id="BD_FLEXSITEMDETAILV",
                field_keys=_AUX_FIELDS,
                filter_string=aux_filter,
                limit=_AUX_BATCH_SIZE,
            ),
        )

        codes: set[str] = {r["FNumber"] for r in bd_rows if r.get("FNumber")}

        if aux_rows:
            aux_ids = [str(int(r["FID"])) for r in aux_rows if r.get("FID")]
            if aux_ids:
                in_clause = ",".join(aux_ids)
                inv_rows = await self.client.query(
                    form_id="STK_Inventory",
                    field_keys=["FMaterialId.FNumber"],
                    filter_string=f"FAuxPropId IN ({in_clause}) and FBaseQty <> 0",
                    limit=2000,
                )
                codes |= {r["FMaterialId.FNumber"] for r in inv_rows if r.get("FMaterialId.FNumber")}

        return codes

    async def _fetch_materials_by_codes(
        self, codes: list[str], erp_clause: str = ""
    ) -> list[dict]:
        """Fetch BD_MATERIAL metadata for a list of codes via IN clause."""
        if not codes:
            return []
        in_clause = ",".join(f"'{c}'" for c in codes)
        return await self.client.query(
            form_id="BD_MATERIAL",
            field_keys=_BD_MATERIAL_FIELDS,
            filter_string=f"FNumber IN ({in_clause}) and FForbidStatus = 'A'{erp_clause}",
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
