#!/usr/bin/env python3
"""Load-test the LIVE MTO path memory footprint (no Kingdee ERP contact).

Purpose: answer "if we delete the SQLite cache and serve live-only, does the
process fit the CVM 512M container ceiling?" — see docs/PLAN_stabilize / health audit.

How it stays safe: it drives the REAL _fetch_live aggregation (real Pydantic
models, real dedup/grouping, real _bom_row_to_child) but replaces the Kingdee
CLIENT with a stub that synthesizes payloads of configurable size. It NEVER calls
the production ERP. Each concurrent request builds FRESH model objects (as the real
readers would when parsing a fresh response), so per-request memory scales with
concurrency exactly as in production.

It sweeps payload SCALE (realistic / large / extreme) × CONCURRENCY (1/3/6/12) and
reports peak RSS, so we can read off "fits up to an MTO of size X at concurrency Y".

Run:  .venv/bin/python scripts/loadtest_live_memory.py
      (or inside the 512M container — see the companion docker invocation)
"""
import asyncio
import gc
import logging
import os
import resource
import sys
import threading
import time
from decimal import Decimal

logging.disable(logging.CRITICAL)  # silence per-row handler WARNINGs; measure pure data-path memory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mto_config import MTOConfig  # noqa: E402
from src.query.mto_handler import MTOQueryHandler as MTOHandler  # noqa: E402
from src.readers.models import (  # noqa: E402
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

FETCH_LATENCY_S = float(os.environ.get("FETCH_LATENCY_S", "0.8"))  # simulate Kingdee 1-5s so requests overlap

# Payload profiles: row counts per form. "realistic" is generous for a big MTO;
# "extreme" is ~10x any real MTO — if that fits, live-only fits with huge margin.
SCALES = {
    "realistic": {"bom": 80, "prod_recv": 400, "pur_recv": 300, "pur": 120,
                  "sub": 40, "pick": 120, "deliv": 120, "prd_mo": 40, "sales": 30},
    "large":     {"bom": 240, "prod_recv": 1200, "pur_recv": 900, "pur": 360,
                  "sub": 120, "pick": 360, "deliv": 360, "prd_mo": 120, "sales": 90},
    "extreme":   {"bom": 800, "prod_recv": 4000, "pur_recv": 3000, "pur": 1200,
                  "sub": 400, "pick": 1200, "deliv": 1200, "prd_mo": 400, "sales": 300},
}
CONCURRENCIES = [1, 3, 6, 12]
MTO = "AK2510034"


def _d(x):
    return Decimal(str(x))


def _build_lists(counts):
    """Build FRESH model lists with VARIED keys so aggregation grows realistically."""
    # self-made (05) + purchased (03) codes for BOM; finished-goods (07) for sales
    sm = [f"05.02.{i:03d}" for i in range(counts["bom"] // 2 + 1)]
    pu = [f"03.01.{i:03d}" for i in range(counts["bom"] // 2 + 1)]
    bom_codes = (sm + pu)[: counts["bom"]] or ["05.02.000"]
    fin_codes = [f"07.01.{i:03d}" for i in range(max(1, counts["sales"]))]

    def code(i):
        return bom_codes[i % len(bom_codes)]

    bom = [ProductionBOMModel(mo_bill_no=f"MO{i:05d}", mto_number=MTO, material_code=code(i),
                              material_name=f"件{i}", specification="规格", aux_prop_id=i % 50,
                              material_type=1, need_qty=_d(100), picked_qty=_d(50), no_picked_qty=_d(50))
           for i in range(counts["bom"])]
    prd_mo = [ProductionOrderModel(bill_no=f"MO{i:05d}", mto_number=MTO, workshop="车间A",
                                   material_code=code(i), material_name=f"件{i}", specification="规格",
                                   aux_prop_id=i % 50, qty=_d(100), status="B")
              for i in range(counts["prd_mo"])]
    prod_recv = [ProductionReceiptModel(bill_no=f"RK{i:06d}", mto_number=MTO, material_code=code(i),
                                        real_qty=_d(10), must_qty=_d(10), aux_prop_id=i % 50,
                                        mo_bill_no=f"MO{i % max(1, counts['prd_mo']):05d}")
                 for i in range(counts["prod_recv"])]
    pur_recv = [PurchaseReceiptModel(bill_no=f"PR{i:06d}", mto_number=MTO, material_code=code(i),
                                     real_qty=_d(10), must_qty=_d(10), bill_type_number="RKD01_SYS",
                                     aux_prop_id=i % 50)
                for i in range(counts["pur_recv"])]
    pur = [PurchaseOrderModel(bill_no=f"PO{i:05d}", mto_number=MTO, material_code=code(i),
                              aux_prop_id=i % 50, order_qty=_d(100), stock_in_qty=_d(40),
                              remain_stock_in_qty=_d(60))
           for i in range(counts["pur"])]
    sub = [SubcontractingOrderModel(bill_no=f"SUB{i:05d}", mto_number=MTO, material_code=code(i),
                                    order_qty=_d(100), stock_in_qty=_d(30), no_stock_in_qty=_d(70),
                                    aux_prop_id=i % 50)
           for i in range(counts["sub"])]
    pick = [MaterialPickingModel(bill_no=f"PK{i:05d}", mto_number=MTO, material_code=code(i),
                                 app_qty=_d(50), actual_qty=_d(50), ppbom_bill_no=f"BOM{i:05d}",
                                 aux_prop_id=i % 50)
            for i in range(counts["pick"])]
    deliv = [SalesDeliveryModel(bill_no=f"DL{i:05d}", mto_number=MTO, material_code=fin_codes[i % len(fin_codes)],
                                real_qty=_d(5), must_qty=_d(5), aux_prop_id=i % 50)
             for i in range(counts["deliv"])]
    sales = [SalesOrderModel(bill_no=f"SO{i:05d}", mto_number=MTO, material_code=fin_codes[i % len(fin_codes)],
                             customer_name="客户X", aux_prop_id=i % 50, qty=_d(200), bom_short_name="简称")
             for i in range(counts["sales"])]
    return {"production_bom": bom, "production_order": prd_mo, "production_receipt": prod_recv,
            "purchase_receipt": pur_recv, "purchase_order": pur, "subcontracting_order": sub,
            "material_picking": pick, "sales_delivery": deliv, "sales_order": sales}


class StubClient:
    async def lookup_aux_properties(self, ids):
        return {i: f"颜色{i}-尺寸{i}" for i in ids}

    async def lookup_material_categories(self, material_codes):
        # Mirror the real client's {code: category_name} return (added Phase 2a,
        # commit 80d52b8). Cycle through realistic categories so the live path's
        # non-自制 override filter keeps a representative subset — exercising the
        # category-routing branch in _build_bom_joined_rows_from_live rather than
        # short-circuiting it (which would understate memory).
        cats = ("外销包材", "委外加工", "主料", "半成品", "包装成品")
        return {c: cats[i % len(cats)] for i, c in enumerate(material_codes)}


class StubReader:
    """Rebuilds fresh model objects every call (like the real reader parsing a fresh response)."""
    def __init__(self, key, counts, client=None):
        self._key = key
        self._counts = counts
        self.client = client

    async def fetch_by_mto(self, mto_number):
        await asyncio.sleep(FETCH_LATENCY_S)  # simulate Kingdee round-trip so requests overlap
        return _build_lists(self._counts)[self._key]


def make_handler(counts):
    client = StubClient()
    keys = ["production_order", "production_bom", "production_receipt", "purchase_order",
            "purchase_receipt", "subcontracting_order", "material_picking", "sales_delivery", "sales_order"]
    readers = {k: StubReader(k, counts, client=client) for k in keys}
    return MTOHandler(
        production_order_reader=readers["production_order"],
        production_bom_reader=readers["production_bom"],
        production_receipt_reader=readers["production_receipt"],
        purchase_order_reader=readers["purchase_order"],
        purchase_receipt_reader=readers["purchase_receipt"],
        subcontracting_order_reader=readers["subcontracting_order"],
        material_picking_reader=readers["material_picking"],
        sales_delivery_reader=readers["sales_delivery"],
        sales_order_reader=readers["sales_order"],
        cache_reader=None,
        mto_config=MTOConfig(),
        metric_engine=None,          # metrics add modest per-child dicts; documented as a slight under-count
        memory_cache_enabled=False,  # measure the pure live path, force every request to recompute
    )


# ---- RSS sampling (Linux /proc preferred; macOS falls back to ru_maxrss) ----
def rss_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0  # kB -> MB
    except FileNotFoundError:
        pass
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return ru / (1024 * 1024) if sys.platform == "darwin" else ru / 1024.0  # mac bytes / linux kB


class PeakSampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak = 0.0
        self._run = True

    def run(self):
        while self._run:
            self.peak = max(self.peak, rss_mb())
            time.sleep(0.01)

    def stop(self):
        self._run = False


async def run_case(counts, concurrency):
    handler = make_handler(counts)
    gc.collect()
    base = rss_mb()
    sampler = PeakSampler()
    sampler.start()
    await asyncio.gather(*[handler.get_status(MTO, use_cache=False) for _ in range(concurrency)])
    sampler.stop()
    sampler.join()
    peak = max(sampler.peak, rss_mb())
    del handler
    gc.collect()
    return base, peak


async def main():
    print(f"platform={sys.platform}  python={sys.version.split()[0]}  fetch_latency={FETCH_LATENCY_S}s")
    print(f"baseline RSS after imports+construct: {rss_mb():.1f} MB")
    print(f"{'scale':<10}{'rows/req':>10}{'conc':>6}{'baseRSS':>10}{'peakRSS':>10}{'vs512':>10}")
    for scale, counts in SCALES.items():
        rows = sum(counts.values())
        for conc in CONCURRENCIES:
            base, peak = await run_case(counts, conc)
            verdict = "OK" if peak < 512 else "OVER"
            print(f"{scale:<10}{rows:>10}{conc:>6}{base:>9.1f}{peak:>9.1f}{'  ' + verdict + ' (' + str(round(peak/512*100)) + '%)':>14}")


if __name__ == "__main__":
    asyncio.run(main())
