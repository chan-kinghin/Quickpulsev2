"""Cache/live path parity guard — executes BOTH real builders on mirrored fixtures.

History: the previous version of this file built cache_row and live_row from the
SAME `_make_bom_joined_row(**kwargs)` helper and asserted equality — a tautology
that could never fail for a real divergence. The is_purchase live drop
(AS2603021), the Tier-2 dedup asymmetry, and the MAX/SUM need_qty asymmetry all
shipped green under it (audit 2026-06-10, data-path family). This rewrite runs
the two REAL implementations on equivalent fixture documents:

- LIVE:  the full `MTOQueryHandler.get_status(use_cache=False)` pipeline with
  mocked reader payloads; the output of `_build_bom_joined_rows_from_live`
  (including the `lookup_material_categories` wiring in `_fetch_live`) is
  captured via a pass-through spy.
- CACHE: a real SQLite database initialized from `src/database/schema.sql`
  (+ migrations) and seeded with INSERTs mirroring the exact same fixture
  documents, queried through `CacheReader.get_mto_bom_joined`.

SCOPE — deliberate exclusions:
- Parity is asserted for Step-1 BOM rows only (materials present in PPBOM)
  plus a presence/value check on the live block-2b synthetic row (PUR-only
  material). The cache path intentionally has NO 2a/2c/2d synthetic blocks
  (its 2b-equivalent is built as ChildItems in `_try_cache`, not as
  BOMJoinedRows) and `get_mto_bom_joined` is slated for deletion after the
  live cutover bakes — so the synthetic blocks are out of scope here.
- has_purchase_order / has_subcontract_order tri-state: BOTH paths now set it
  (live `_make_row`; cache SQL columns 31/32 since the Pattern-7 cache fix,
  2026-06-10) — equality is asserted in PARITY_FIELDS and pinned per-row in
  test_tri_state_order_provenance. (Historically the cache left these None —
  a live/cache half-fix this file exists to catch.)
- KNOWN UNFIXED divergence (verified live=600 vs cache=300, 2026-06-10): a
  material_type=1 code with NO PRD_MO appearing on MULTIPLE parent PPBOM
  lines gets need_qty=SUM on live (audit fix in `_build_bom_joined_rows_
  from_live`) but MAX on cache (`COALESCE(mo_all.mo_qty, br.max_need_qty)`
  in bom_agg). The fixtures here deliberately use single PPBOM lines for
  no-MO codes (MAX==SUM) so this file stays green; the cache side belongs
  to the get_mto_bom_joined deletion plan, not to this guard.

A guard that cannot fail is the disease this file cures: see
TestParityGuardCanFail, which feeds a deliberately divergent fixture and
asserts the comparison detects it.
"""

import copy
from dataclasses import fields as dataclass_fields
from decimal import Decimal
from unittest.mock import AsyncMock

from src.query.cache_reader import BOMJoinedRow, CacheReader
from src.query.mto_handler import MTOQueryHandler
from src.readers.models import (
    MaterialPickingModel,
    ProductionBOMModel,
    ProductionOrderModel,
    ProductionReceiptModel,
    PurchaseOrderModel,
    PurchaseReceiptModel,
    SubcontractingOrderModel,
)

MTO = "AS2606001"

# Materials under test (all Step-1 / in PPBOM except M4):
#   M1 05.02.001  self-made part — PRD_MO target overrides BOM need_qty
#   M2 06.03.001  purchased packaging (外销包材, is_purchase=True) — PO + STK
#   M3 05.10.003  subcontracted (委外加工) at a specific aux
#   M4 03.23.009  PUR-only, NOT in PPBOM — live block-2b synthetic row
M1, M2, M3, M4 = "05.02.001", "06.03.001", "05.10.003", "03.23.009"
M3_AUX, M4_AUX = 2002, 3001

# BD_MATERIAL master data for the live `lookup_material_categories` mock.
# The cache equivalent is denormalized onto cached_production_bom rows by the
# sync writer — kept consistent with the BOM docs below.
MASTER_DATA = {
    M1: ("半成品", False),
    M2: ("外销包材", True),
    M4: ("外销包材", True),
}

AUX_DESCRIPTIONS = {M3_AUX: "蓝色-L", M4_AUX: "红色"}


def make_fixture_docs() -> dict:
    """Canonical fixture documents, defined ONCE.

    Keys mirror the reader names; each doc dict doubles as (a) kwargs for the
    live reader model and (b) the source for the cache INSERT — so both paths
    are guaranteed to see the same documents.
    """
    return {
        "production_bom": [
            # M1: need_qty=999 is a deliberate lie — both paths must override
            # it with the PRD_MO target (120). Catches Pattern-10 regressions.
            dict(mo_bill_no="MO0001", mto_number=MTO, material_code=M1,
                 material_name="硅胶头带", specification="SpecA",
                 aux_attributes="", aux_prop_id=0, material_type=1,
                 material_group_name="硅胶件", category_name="半成品",
                 is_purchase=False, need_qty=999, picked_qty=50,
                 no_picked_qty=70),
            dict(mo_bill_no="MO0001", mto_number=MTO, material_code=M2,
                 material_name="外箱", specification="K=K 600x400",
                 aux_attributes="", aux_prop_id=0, material_type=1,
                 material_group_name="纸箱", category_name="外销包材",
                 is_purchase=True, need_qty=300, picked_qty=0,
                 no_picked_qty=300),
            dict(mo_bill_no="MO0001", mto_number=MTO, material_code=M3,
                 material_name="电镀镜片", specification="SpecC",
                 aux_attributes="蓝色-L", aux_prop_id=M3_AUX, material_type=3,
                 material_group_name="镜片", category_name="委外加工",
                 is_purchase=False, need_qty=80, picked_qty=0,
                 no_picked_qty=80),
        ],
        "production_order": [
            dict(bill_no="MO0001", mto_number=MTO, workshop="一车间",
                 material_code="07.01.001", material_name="成品泳镜",
                 specification="F", aux_attributes="", aux_prop_id=0,
                 qty=120, status="C", create_date="2026-06-01"),
            # M1's own production order — the authoritative demand (120).
            dict(bill_no="MO0002", mto_number=MTO, workshop="二车间",
                 material_code=M1, material_name="硅胶头带",
                 specification="SpecA", aux_attributes="", aux_prop_id=0,
                 qty=120, status="C", create_date="2026-06-01"),
        ],
        "production_receipt": [
            dict(bill_no="RK001", mto_number=MTO, material_code=M1,
                 real_qty=40, must_qty=40, aux_prop_id=0, entry_id=1),
            dict(bill_no="RK002", mto_number=MTO, material_code=M1,
                 real_qty=30, must_qty=35, aux_prop_id=0, entry_id=1),
        ],
        "material_picking": [
            dict(bill_no="LL001", mto_number=MTO, material_code=M1,
                 app_qty=33, actual_qty=30, ppbom_bill_no="PPBOM001",
                 aux_prop_id=0, entry_id=1),
            dict(bill_no="LL002", mto_number=MTO, material_code=M1,
                 app_qty=22, actual_qty=20, ppbom_bill_no="PPBOM001",
                 aux_prop_id=0, entry_id=1),
        ],
        "purchase_order": [
            # Same PO document, two entry lines for the same (material, aux)
            # — entry-line grain (Pattern 5 / migration 019). Both paths must
            # sum to 280 / 250.
            dict(bill_no="PO001", mto_number=MTO, material_code=M2,
                 material_name="外箱", specification="K=K 600x400",
                 aux_attributes="", aux_prop_id=0, order_qty=180,
                 stock_in_qty=150, remain_stock_in_qty=30, entry_id=1),
            dict(bill_no="PO001", mto_number=MTO, material_code=M2,
                 material_name="外箱", specification="K=K 600x400",
                 aux_attributes="", aux_prop_id=0, order_qty=100,
                 stock_in_qty=100, remain_stock_in_qty=0, entry_id=2),
            # M4: PUR-only material, no PPBOM line → live block-2b synthetic.
            dict(bill_no="PO002", mto_number=MTO, material_code=M4,
                 material_name="贴纸", specification="红色贴纸",
                 aux_attributes="红色", aux_prop_id=M4_AUX, order_qty=500,
                 stock_in_qty=450, remain_stock_in_qty=50, entry_id=1),
        ],
        "purchase_receipt": [
            dict(bill_no="RKD001", mto_number=MTO, material_code=M2,
                 real_qty=250, must_qty=280, bill_type_number="RKD01_SYS",
                 aux_prop_id=0, entry_id=1),
            dict(bill_no="RKD002", mto_number=MTO, material_code=M4,
                 real_qty=450, must_qty=500, bill_type_number="RKD01_SYS",
                 aux_prop_id=M4_AUX, entry_id=1),
        ],
        "subcontracting_order": [
            dict(bill_no="WW001", mto_number=MTO, material_code=M3,
                 order_qty=80, stock_in_qty=60, no_stock_in_qty=20,
                 aux_prop_id=M3_AUX, entry_id=1),
        ],
        "sales_delivery": [],
        "sales_order": [],
    }


# ============================================================================
# Live path driver
# ============================================================================


def _live_models(docs: dict) -> dict:
    model_for = {
        "production_bom": ProductionBOMModel,
        "production_order": ProductionOrderModel,
        "production_receipt": ProductionReceiptModel,
        "material_picking": MaterialPickingModel,
        "purchase_order": PurchaseOrderModel,
        "purchase_receipt": PurchaseReceiptModel,
        "subcontracting_order": SubcontractingOrderModel,
    }
    return {
        name: [model(**d) for d in docs.get(name, [])]
        for name, model in model_for.items()
    } | {"sales_delivery": [], "sales_order": []}


def _make_handler(mock_readers) -> MTOQueryHandler:
    return MTOQueryHandler(
        production_order_reader=mock_readers["production_order"],
        production_bom_reader=mock_readers["production_bom"],
        production_receipt_reader=mock_readers["production_receipt"],
        purchase_order_reader=mock_readers["purchase_order"],
        purchase_receipt_reader=mock_readers["purchase_receipt"],
        subcontracting_order_reader=mock_readers["subcontracting_order"],
        material_picking_reader=mock_readers["material_picking"],
        sales_delivery_reader=mock_readers["sales_delivery"],
        sales_order_reader=mock_readers["sales_order"],
    )


async def _run_live(mock_readers, docs: dict) -> list[BOMJoinedRow]:
    """Run the REAL live pipeline end-to-end and capture its BOMJoinedRows.

    Drives `get_status(use_cache=False)` → `_fetch_live`, so the
    `lookup_material_categories` / is_purchase wiring (the AS2603021 gap)
    is exercised, not just the builder in isolation.
    """
    models = _live_models(docs)
    for name, payload in models.items():
        mock_readers[name].fetch_by_mto = AsyncMock(return_value=payload)

    client = mock_readers["production_order"].client
    client.lookup_aux_properties = AsyncMock(return_value=dict(AUX_DESCRIPTIONS))
    client.lookup_material_categories = AsyncMock(return_value=dict(MASTER_DATA))

    handler = _make_handler(mock_readers)
    captured: list[BOMJoinedRow] = []
    original = handler._build_bom_joined_rows_from_live

    def _capture(*args, **kwargs):
        rows = original(*args, **kwargs)
        captured.extend(rows)
        return rows

    handler._build_bom_joined_rows_from_live = _capture
    await handler.get_status(MTO, use_cache=False)
    return captured


# ============================================================================
# Cache path driver
# ============================================================================


async def _seed_cache(db, docs: dict) -> None:
    """INSERT the same fixture documents into the real schema.sql tables."""
    await db.executemany(
        """INSERT INTO cached_production_bom
           (mo_bill_no, mto_number, material_code, material_name, specification,
            aux_attributes, aux_prop_id, material_type, material_group_name,
            category_name, is_purchase, need_qty, picked_qty, no_picked_qty)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(d["mo_bill_no"], d["mto_number"], d["material_code"],
          d["material_name"], d["specification"], d["aux_attributes"],
          d["aux_prop_id"], d["material_type"], d["material_group_name"],
          d["category_name"], int(d["is_purchase"]), d["need_qty"],
          d["picked_qty"], d["no_picked_qty"])
         for d in docs["production_bom"]],
    )
    await db.executemany(
        """INSERT INTO cached_production_orders
           (bill_no, mto_number, workshop, material_code, material_name,
            specification, aux_attributes, aux_prop_id, qty, status, create_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [(d["bill_no"], d["mto_number"], d["workshop"], d["material_code"],
          d["material_name"], d["specification"], d["aux_attributes"],
          d["aux_prop_id"], d["qty"], d["status"], d["create_date"])
         for d in docs["production_order"]],
    )
    await db.executemany(
        """INSERT INTO cached_production_receipts
           (bill_no, mto_number, material_code, real_qty, must_qty,
            aux_prop_id, entry_id)
           VALUES (?,?,?,?,?,?,?)""",
        [(d["bill_no"], d["mto_number"], d["material_code"], d["real_qty"],
          d["must_qty"], d["aux_prop_id"], d["entry_id"])
         for d in docs["production_receipt"]],
    )
    await db.executemany(
        """INSERT INTO cached_material_picking
           (bill_no, mto_number, material_code, app_qty, actual_qty,
            ppbom_bill_no, aux_prop_id, entry_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        [(d["bill_no"], d["mto_number"], d["material_code"], d["app_qty"],
          d["actual_qty"], d["ppbom_bill_no"], d["aux_prop_id"], d["entry_id"])
         for d in docs["material_picking"]],
    )
    await db.executemany(
        """INSERT INTO cached_purchase_orders
           (bill_no, mto_number, material_code, material_name, specification,
            aux_attributes, aux_prop_id, order_qty, stock_in_qty,
            remain_stock_in_qty, entry_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [(d["bill_no"], d["mto_number"], d["material_code"], d["material_name"],
          d["specification"], d["aux_attributes"], d["aux_prop_id"],
          d["order_qty"], d["stock_in_qty"], d["remain_stock_in_qty"],
          d["entry_id"])
         for d in docs["purchase_order"]],
    )
    await db.executemany(
        """INSERT INTO cached_purchase_receipts
           (bill_no, mto_number, material_code, real_qty, must_qty,
            bill_type_number, aux_prop_id, entry_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        [(d["bill_no"], d["mto_number"], d["material_code"], d["real_qty"],
          d["must_qty"], d["bill_type_number"], d["aux_prop_id"], d["entry_id"])
         for d in docs["purchase_receipt"]],
    )
    await db.executemany(
        """INSERT INTO cached_subcontracting_orders
           (bill_no, mto_number, material_code, order_qty, stock_in_qty,
            no_stock_in_qty, aux_prop_id, entry_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        [(d["bill_no"], d["mto_number"], d["material_code"], d["order_qty"],
          d["stock_in_qty"], d["no_stock_in_qty"], d["aux_prop_id"],
          d["entry_id"])
         for d in docs["subcontracting_order"]],
    )


async def _run_cache(test_database, docs: dict) -> list[BOMJoinedRow]:
    """Seed the real schema and run the REAL cache builder."""
    await _seed_cache(test_database, docs)
    reader = CacheReader(test_database, ttl_minutes=60)
    result = await reader.get_mto_bom_joined(MTO)
    return result.data


# ============================================================================
# Comparison helper (shared by the parity test AND the can-fail test)
# ============================================================================

# Per-field value parity. has_purchase_order / has_subcontract_order ARE in
# the set since the Pattern-7 cache fix (2026-06-10): both paths must resolve
# the tri-state to the same True/False; per-row values are additionally pinned
# in test_tri_state_order_provenance so agreement can't be vacuous.
PARITY_FIELDS = (
    "mo_bill_no", "mto_number", "material_name", "specification",
    "aux_attributes", "material_type", "need_qty", "picked_qty",
    "no_picked_qty", "prod_receipt_real_qty", "prod_receipt_must_qty",
    "pick_actual_qty", "pick_app_qty", "purchase_order_qty",
    "purchase_stock_in_qty", "purchase_receipt_real_qty",
    "subcontract_order_qty", "subcontract_stock_in_qty", "delivery_real_qty",
    "material_group_name", "category_name", "is_purchase",
    "match_quality_breakdown", "has_purchase_order", "has_subcontract_order",
)


def _index_rows(rows: list[BOMJoinedRow]) -> dict[tuple[str, int], BOMJoinedRow]:
    indexed: dict[tuple[str, int], BOMJoinedRow] = {}
    for r in rows:
        key = (r.material_code, r.aux_prop_id)
        assert key not in indexed, f"duplicate (code, aux) row emitted: {key}"
        indexed[key] = r
    return indexed


def _compare(cache_rows: list[BOMJoinedRow],
             live_rows: list[BOMJoinedRow]) -> list[str]:
    """Return human-readable mismatch strings; empty list == parity holds."""
    cache_by_key = _index_rows(cache_rows)
    live_by_key = _index_rows(live_rows)
    mismatches = []
    for key in sorted(cache_by_key):
        if key not in live_by_key:
            mismatches.append(f"{key}: present in cache, missing in live")
            continue
        c_row, l_row = cache_by_key[key], live_by_key[key]
        for f in PARITY_FIELDS:
            cv, lv = getattr(c_row, f), getattr(l_row, f)
            # Decimal("70.0") == Decimal("70") numerically — SQLite REAL
            # round-trips add trailing zeros; that is not a divergence.
            if cv != lv:
                mismatches.append(f"{key}.{f}: cache={cv!r} live={lv!r}")
    return mismatches


# ============================================================================
# Two-path parity tests
# ============================================================================


class TestCacheLiveBuilderParity:
    """Both REAL builders, mirrored fixtures, per-field equality."""

    async def test_step1_bom_rows_match_field_by_field(
        self, mock_readers, test_database
    ):
        docs = make_fixture_docs()
        live_rows = await _run_live(mock_readers, docs)
        cache_rows = await _run_cache(test_database, docs)

        # Every cache BOM row must have a live counterpart; the only live
        # extra is the block-2b synthetic for the PUR-only material M4.
        cache_keys = set(_index_rows(cache_rows))
        live_keys = set(_index_rows(live_rows))
        assert cache_keys == {(M1, 0), (M2, 0), (M3, M3_AUX)}
        assert live_keys - cache_keys == {(M4, M4_AUX)}

        mismatches = _compare(cache_rows, live_rows)
        assert not mismatches, "cache/live divergence:\n" + "\n".join(mismatches)

        # Pin a few absolute values so agreement can't be vacuous
        # (both-paths-emit-zero would also "match").
        live = _index_rows(live_rows)
        assert live[(M1, 0)].need_qty == Decimal("120")  # PRD_MO override, not 999
        assert live[(M1, 0)].prod_receipt_real_qty == Decimal("70")
        assert live[(M1, 0)].pick_actual_qty == Decimal("50")
        assert live[(M2, 0)].purchase_order_qty == Decimal("280")  # 2 entry lines
        assert live[(M2, 0)].purchase_receipt_real_qty == Decimal("250")
        assert live[(M2, 0)].is_purchase is True
        assert live[(M3, M3_AUX)].subcontract_stock_in_qty == Decimal("60")

    async def test_live_2b_synthetic_row_for_pur_only_material(
        self, mock_readers
    ):
        """Block-2b equivalent: the cache path emits this as a ChildItem in
        _try_cache (out of BOMJoinedRow scope); on the live side assert the
        synthetic row carries the master-data is_purchase — the exact field
        the AS2603021 regression dropped."""
        live_rows = await _run_live(mock_readers, make_fixture_docs())
        row = _index_rows(live_rows)[(M4, M4_AUX)]
        assert row.material_type == 2
        assert row.is_purchase is True  # from lookup_material_categories
        assert row.category_name == "外销包材"
        assert row.need_qty == Decimal("0")
        assert row.purchase_order_qty == Decimal("500")
        assert row.purchase_stock_in_qty == Decimal("450")
        assert row.purchase_receipt_real_qty == Decimal("450")

    async def test_tri_state_order_provenance(self, mock_readers, test_database):
        """Pattern-7 cache fix (2026-06-10): BOTH paths resolve the tri-state
        to True/False from the code-level order rollup — the cache may never
        leave it None again (the legacy None kept the or-fallback, repainting
        Wave-5B deliberate zeros with need_qty on ?source=cache)."""
        docs = make_fixture_docs()
        live_rows = await _run_live(mock_readers, docs)
        cache_rows = await _run_cache(test_database, docs)

        # Pin absolute values on BOTH paths (not just equality, which a
        # both-None bug would also satisfy).
        for label, indexed in (("live", _index_rows(live_rows)),
                               ("cache", _index_rows(cache_rows))):
            assert indexed[(M1, 0)].has_purchase_order is False, label
            assert indexed[(M1, 0)].has_subcontract_order is False, label
            assert indexed[(M2, 0)].has_purchase_order is True, label
            assert indexed[(M2, 0)].has_subcontract_order is False, label
            assert indexed[(M3, M3_AUX)].has_purchase_order is False, label
            assert indexed[(M3, M3_AUX)].has_subcontract_order is True, label

        # Block-2b synthetic (PUR-only material) exists on live only.
        assert _index_rows(live_rows)[(M4, M4_AUX)].has_purchase_order is True


class TestParityGuardCanFail:
    """Prove the comparison DETECTS a real divergence.

    The previous guard built both rows from one helper and literally could
    not fail — which is how the is_purchase live gap shipped green. Here the
    live side is fed a fixture where the PPBOM model lost its is_purchase
    flag (the historical bug shape) while the cache keeps the truth; the
    comparison must flag it.
    """

    async def test_detects_is_purchase_divergence(
        self, mock_readers, test_database
    ):
        cache_docs = make_fixture_docs()
        live_docs = copy.deepcopy(cache_docs)
        # Simulate the live path dropping master data: M2's PPBOM model says
        # is_purchase=False while the cache row keeps the synced True.
        for bom in live_docs["production_bom"]:
            if bom["material_code"] == M2:
                bom["is_purchase"] = False

        live_rows = await _run_live(mock_readers, live_docs)
        cache_rows = await _run_cache(test_database, cache_docs)

        mismatches = _compare(cache_rows, live_rows)
        assert any(
            "is_purchase" in m and M2 in m for m in mismatches
        ), f"guard failed to detect the is_purchase divergence: {mismatches}"
        # And ONLY that divergence — the rest of the fixture still matches.
        assert all("is_purchase" in m for m in mismatches), mismatches

    async def test_detects_quantity_divergence(self, mock_readers, test_database):
        """Second failure mode: a receipt document visible to one path only
        (the Tier-2 dedup / N× family is a quantity-side disease)."""
        cache_docs = make_fixture_docs()
        live_docs = copy.deepcopy(cache_docs)
        # Live misses one PRD_INSTOCK batch that the cache has synced.
        live_docs["production_receipt"] = [
            d for d in live_docs["production_receipt"] if d["bill_no"] != "RK002"
        ]

        live_rows = await _run_live(mock_readers, live_docs)
        cache_rows = await _run_cache(test_database, cache_docs)

        mismatches = _compare(cache_rows, live_rows)
        assert any(
            "prod_receipt_real_qty" in m and M1 in m for m in mismatches
        ), f"guard failed to detect the receipt-qty divergence: {mismatches}"


# ============================================================================
# Structure parity (cheap field-name drift check)
# ============================================================================


class TestBOMJoinedRowStructureParity:
    """Verify that BOMJoinedRow has all expected fields for both paths.

    Presence in this set is a structure check ONLY — per-field VALUE parity
    between the two real builders is verified by TestCacheLiveBuilderParity.
    """

    EXPECTED_FIELDS = {
        # BOM core fields
        "mo_bill_no",
        "mto_number",
        "material_code",
        "material_name",
        "specification",
        "aux_attributes",
        "aux_prop_id",
        "material_type",
        "need_qty",
        "picked_qty",
        "no_picked_qty",
        # Production receipts (PRD_INSTOCK)
        "prod_receipt_real_qty",
        "prod_receipt_must_qty",
        # Material picking (PRD_PickMtrl)
        "pick_actual_qty",
        "pick_app_qty",
        # Purchase orders (PUR_PurchaseOrder)
        "purchase_order_qty",
        "purchase_stock_in_qty",
        # Purchase receipts (STK_InStock)
        "purchase_receipt_real_qty",
        # Subcontracting orders (SUB_POORDER)
        "subcontract_order_qty",
        "subcontract_stock_in_qty",
        # Sales delivery (SAL_OUTSTOCK)
        "delivery_real_qty",
        # Per-source aux match quality (commit 8e0f644)
        "match_quality_breakdown",
        # Display routing — material grouping / category / purchase split
        # (commit 2724bcf)
        "material_group_name",
        "category_name",
        "is_purchase",
        # Tri-state order provenance (Pattern 7, audit 2026-06-10) — BOTH
        # paths set True/False (see test_tri_state_order_provenance)
        "has_purchase_order",
        "has_subcontract_order",
    }

    def test_bom_joined_row_has_all_expected_fields(self):
        """BOMJoinedRow dataclass must have every field both paths rely on."""
        actual_fields = {f.name for f in dataclass_fields(BOMJoinedRow)}
        missing = self.EXPECTED_FIELDS - actual_fields
        assert not missing, f"BOMJoinedRow missing fields: {missing}"

    def test_no_unexpected_extra_fields(self):
        """Catch new fields added to BOMJoinedRow that tests don't cover."""
        actual_fields = {f.name for f in dataclass_fields(BOMJoinedRow)}
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not extra, (
            f"BOMJoinedRow has new fields not in parity check: {extra}. "
            "Add them to EXPECTED_FIELDS here AND to PARITY_FIELDS / the "
            "tri-state test above if both paths must agree on the value."
        )
