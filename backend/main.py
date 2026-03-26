import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from data_loader import load_all_data, FOLDER_TABLE_MAP
from database import Database
from graph_service import GraphService
from llm_service import LLMService

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "o2c_data.db")
DATA_ROOT = os.getenv("DATA_ROOT", "../sap-order-to-cash-dataset/sap-o2c-data")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

db: Database = None
graph_svc: GraphService = None
llm_svc: LLMService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, graph_svc, llm_svc

    print("🚀 Starting SAP O2C Graph System...")

    # Load data if DB doesn't exist or is empty
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 1000:
        print(f"📦 Loading data from {DATA_ROOT}...")
        if os.path.exists(DATA_ROOT):
            counts = load_all_data(DB_PATH, DATA_ROOT)
            print(f"✅ Data loaded: {sum(counts.values())} total records")
        else:
            print(f"⚠️  Data directory not found: {DATA_ROOT}")
            print("   Please set DATA_ROOT env var to your sap-o2c-data folder path")

    db = Database(DB_PATH)
    graph_svc = GraphService(DB_PATH)

    if GEMINI_API_KEY:
        schema = db.get_schema_summary()
        llm_svc = LLMService(GEMINI_API_KEY, schema)
        print("✅ LLM service ready (Gemini)")
    else:
        print("⚠️  GEMINI_API_KEY not set — chat will be disabled")

    print("✅ System ready!")
    yield
    print("👋 Shutting down...")


app = FastAPI(title="SAP O2C Graph System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    counts = db.get_entity_counts() if db else {}
    return {
        "status": "ok",
        "llm_ready": llm_svc is not None,
        "entity_counts": counts,
    }


# ─── Graph APIs ──────────────────────────────────────────────────────────────

@app.get("/api/graph/overview")
def graph_overview():
    """High-level O2C flow graph with entity type nodes."""
    return graph_svc.get_overview_graph()


@app.get("/api/graph/expand")
def graph_expand(type: str = Query(...), id: str = Query(None)):
    """Expand an entity type node or a specific entity node."""
    if id is None:
        # Expand entity type → show individual records
        return graph_svc.expand_entity_type(type)
    else:
        # Expand a specific entity → show its neighborhood
        return graph_svc.get_node_neighborhood(type, id)


@app.get("/api/graph/flow/{sales_order}")
def graph_flow(sales_order: str):
    """Get full O2C flow for a specific sales order."""
    return graph_svc.get_full_o2c_flow(sales_order)


@app.get("/api/graph/search")
def graph_search(q: str = Query(...), limit: int = 20):
    """Search for entities by ID or name."""
    results = []

    # Search sales orders
    rows = db.execute_query(
        "SELECT 'SalesOrder' as type, salesOrder as id, soldToParty as detail FROM so_headers WHERE salesOrder LIKE ? LIMIT ?",
        (f"%{q}%", limit // 4)
    )
    results.extend(rows)

    # Search billing docs
    rows = db.execute_query(
        "SELECT 'BillingDocument' as type, billingDocument as id, totalNetAmount as detail FROM bd_headers WHERE billingDocument LIKE ? LIMIT ?",
        (f"%{q}%", limit // 4)
    )
    results.extend(rows)

    # Search deliveries
    rows = db.execute_query(
        "SELECT 'Delivery' as type, deliveryDocument as id, shippingPoint as detail FROM delivery_headers WHERE deliveryDocument LIKE ? LIMIT ?",
        (f"%{q}%", limit // 4)
    )
    results.extend(rows)

    # Search customers
    rows = db.execute_query(
        "SELECT 'Customer' as type, businessPartner as id, businessPartnerName as detail FROM business_partners WHERE businessPartnerName LIKE ? OR businessPartner LIKE ? LIMIT ?",
        (f"%{q}%", f"%{q}%", limit // 4)
    )
    results.extend(rows)

    return {"results": results[:limit]}


# ─── Stats / Summary ─────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    """Returns summary statistics for the dashboard."""
    stats = {}

    # Total amounts
    try:
        row = db.execute_query("SELECT CAST(SUM(CAST(totalNetAmount AS REAL)) AS TEXT) as total FROM bd_headers WHERE billingDocumentIsCancelled != 'True'")
        stats["total_billed"] = row[0]["total"] if row else "0"
    except Exception:
        stats["total_billed"] = "0"

    try:
        row = db.execute_query("SELECT CAST(SUM(CAST(amountInTransactionCurrency AS REAL)) AS TEXT) as total FROM payments")
        stats["total_paid"] = row[0]["total"] if row else "0"
    except Exception:
        stats["total_paid"] = "0"

    # Broken flow: delivered but not billed
    try:
        rows = db.execute_query("""
            SELECT COUNT(DISTINCT sh.salesOrder) as cnt
            FROM so_headers sh
            JOIN delivery_items di ON di.referenceSdDocument = sh.salesOrder
            LEFT JOIN bd_items bi ON bi.referenceSdDocument = (
                SELECT deliveryDocument FROM delivery_items WHERE referenceSdDocument = sh.salesOrder LIMIT 1
            )
            WHERE bi.billingDocument IS NULL
        """)
        stats["unmatched_deliveries"] = rows[0]["cnt"] if rows else 0
    except Exception:
        stats["unmatched_deliveries"] = 0

    # Cancelled billing docs
    try:
        rows = db.execute_query("SELECT COUNT(*) as cnt FROM bd_cancellations")
        stats["cancelled_billing_docs"] = rows[0]["cnt"] if rows else 0
    except Exception:
        stats["cancelled_billing_docs"] = 0

    stats.update(db.get_entity_counts())
    return stats


# ─── Chat API ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Chat endpoint: natural language → SQL → answer."""
    if not llm_svc:
        raise HTTPException(status_code=503, detail="LLM service not configured. Please set GEMINI_API_KEY.")

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    result = llm_svc.chat(req.message, db)
    return result


# ─── Serve Frontend ──────────────────────────────────────────────────────────

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(frontend_dist / "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        file_path = frontend_dist / path
        if file_path.exists():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))

@app.get("/")
def root():
    return {"message": "SAP O2C Graph API is running 🚀"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
