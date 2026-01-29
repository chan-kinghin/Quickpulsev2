# Quickpulse v2: Fresh Start with Proven Architecture

> **Status: COMPLETE** - Archived 2026-01-29. All phases implemented.

---

## Decision

**Start a new project** that preserves the proven architectural patterns from Quickpulse while:
- Using the same Kingdee K3Cloud WebAPI SDK
- Avoiding accumulated technical debt
- Applying lessons learned from v1
- Building performance optimizations in from the start

---

## Project Overview

### What Quickpulse Does
- Syncs and caches sales orders, purchase orders, and instock data from Kingdee K3Cloud
- Provides 2-layer data caching (details, real-time) for fast queries
- Offers natural language query capabilities via DeepSeek LLM
- Supports sales order, purchase order, and instock data queries
- Exports data in JSON, CSV, and Excel formats

### Tech Stack (Keep Same)
| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, SQLite |
| Frontend | Alpine.js, Tailwind CSS |
| External | Kingdee K3Cloud WebAPI SDK, DeepSeek LLM |
| Deployment | Docker Compose, Uvicorn |

---

## Why Fresh Start Makes Sense Here

1. **Technical Debt**: v1 has 209 bare exception handlers, 1,400+ line classes, scattered config
2. **Proven Architecture**: You're not guessing - you know what works
3. **Performance Built-in**: Add pagination, indexes, parallel fetching from day one
4. **Simplified Scope**: Focus only on data sync and caching
5. **Same API**: K3Cloud SDK works, just needs cleaner wrapper

---

## Architecture to Preserve (from Quickpulse v1)

These patterns worked well and should be carried forward:

### 1. Two-Layer Data Architecture ✓
```
Layer 1 (Cache)    → Cached ERP snapshots    → <100ms queries
Layer 2 (Realtime) → Direct API calls        → 1-5s queries
```

### 2. Separation of Concerns ✓
```
readers/      → Data ingestion (API calls)
models/       → Data structures
sync/         → Orchestration (when to fetch/cache)
query/        → Query routing and execution
api/          → HTTP endpoints
frontend/     → Web UI
```

### 3. Tech Stack ✓
- **Backend**: Python + FastAPI + SQLite
- **Frontend**: Alpine.js + Tailwind CSS
- **LLM**: DeepSeek for natural language queries

### 4. Query Intent System ✓
- Parse user intent (LLM or rule-based)
- Route to appropriate data layer
- Format response consistently

---

## Problems to Avoid (Lessons from v1)

| Problem | v1 Issue | v2 Solution |
|---------|----------|-------------|
| Giant classes | QueryRouter: 1,482 lines | Max 200 lines per class |
| Silent failures | 209 bare `except: pass` | Custom exceptions with context |
| Scattered config | `QP_*` env vars everywhere | Single `Config` class |
| Code duplication | Normalization in 10+ places | Dedicated utility module |
| No pagination | Frontend loads all rows | Virtual scrolling from start |
| Sync bottlenecks | Sequential API calls | Parallel fetching |

---

## Quickpulse v2 Project Structure

```
quickpulse-v2/
├── src/
│   ├── __init__.py
│   ├── config.py              # Single config class (env + file)
│   ├── exceptions.py          # Custom exception hierarchy
│   │
│   ├── kingdee/               # K3Cloud API wrapper
│   │   ├── __init__.py
│   │   ├── client.py          # Clean wrapper around SDK
│   │   └── config.py          # Kingdee connection config
│   │
│   ├── readers/               # Data ingestion (one per document type)
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract reader interface
│   │   ├── sales_order.py
│   │   ├── purchase_order.py
│   │   └── instock.py
│   │
│   ├── models/                # Pydantic data models
│   │   ├── __init__.py
│   │   ├── sales_order.py
│   │   ├── purchase_order.py
│   │   └── instock.py
│   │
│   ├── database/              # SQLite layer
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── schema.sql
│   │   └── repositories/      # Data access patterns
│   │       └── cache_repo.py
│   │
│   ├── sync/                  # Sync orchestration
│   │   ├── __init__.py
│   │   ├── scheduler.py
│   │   └── syncer.py
│   │
│   ├── query/                 # Query system
│   │   ├── __init__.py
│   │   ├── router.py          # Main router (small, delegates)
│   │   ├── handlers/          # One handler per query type
│   │   │   ├── mto.py
│   │   │   ├── analytics.py
│   │   │   └── date_range.py
│   │   └── intent/
│   │       ├── parser.py      # LLM intent parsing
│   │       └── rules.py       # Rule-based fallback
│   │
│   └── utils/                 # Shared utilities
│       ├── __init__.py
│       ├── normalization.py   # All string normalization
│       └── dates.py           # Date handling
│
├── api/                       # FastAPI application
│   ├── __init__.py
│   ├── main.py
│   ├── dependencies.py
│   └── routers/
│       ├── query.py
│       ├── sync.py
│       └── admin.py
│
├── frontend/                  # Web UI
│   ├── index.html
│   ├── js/
│   │   └── app.js            # With pagination built-in
│   └── css/
│
├── tests/                     # Mirrors src/ structure
│   ├── test_readers/
│   └── test_query/
│
├── pyproject.toml             # Modern Python packaging
├── .env.example
└── README.md
```

---

## Implementation Phases

### Phase 1: Foundation ✅ COMPLETE
**Goal**: Core infrastructure that everything else builds on

1. **Project setup**
   - Create new repo `quickpulse-v2`
   - Setup `pyproject.toml` with dependencies
   - Create `Config` class with validation

2. **Kingdee client wrapper**
   - Clean wrapper around K3Cloud SDK
   - Centralized connection config
   - Proper error handling with context

3. **Data models**
   - Define Pydantic models (can copy from v1, clean up)
   - Add proper type hints
   - Add validation

4. **Database schema**
   - Copy schema from v1 (it's good)
   - Add indexes from the start
   - Enable WAL mode

**Deliverable**: Can connect to Kingdee API and create database

---

### Phase 2: Data Ingestion ✅ COMPLETE
**Goal**: Fetch and cache data from Kingdee

1. **Readers**
   - Implement `SalesOrderReader`
   - Implement `PurchaseOrderReader`
   - Implement `InstockReader`
   - Clean field mapping (reuse from v1)

2. **Caching layer**
   - Implement cache repositories
   - Bulk insert with batching
   - Full refresh strategy

3. **Basic sync**
   - Manual sync trigger
   - Progress tracking

**Deliverable**: Can fetch data and store in cache tables

---

### Phase 3: Query & API ✅ COMPLETE
**Goal**: Query system and HTTP API

1. **Query handlers**
   - MTO lookup handler
   - Analytics handler
   - Date range handler

2. **Intent parsing**
   - Rule-based parser first
   - LLM parser (optional, can add later)

3. **FastAPI endpoints**
   - Query endpoint
   - Sync endpoint
   - Health check

**Deliverable**: Can query cached data via API

---

### Phase 4: Frontend ✅ COMPLETE
**Goal**: Web UI with performance built-in

1. **Core UI**
   - Copy HTML structure from v1
   - Implement virtual scrolling from start
   - Add pagination to API calls

2. **Filtering**
   - Debounced inputs
   - Client-side filtering for cached data

3. **Polish**
   - Loading states
   - Error handling

**Deliverable**: Full working web application

---

## Migration Strategy

### Option A: Big Bang (Simpler) ✓ USED
1. Build v2 completely
2. Test thoroughly
3. Switch over in one go
4. Keep v1 as fallback

---

## Conclusion

**Decision**: **Fresh start** with new project `quickpulse-v2` ✅ IMPLEMENTED

**All Phases Complete** - System deployed and operational.
