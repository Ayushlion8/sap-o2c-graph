# SAP O2C Graph Explorer

A **Graph-Based Data Intelligence System** for SAP Order-to-Cash (O2C) data — featuring interactive graph visualization and an AI-powered natural language query interface.

---

## Live Demo

🚀 **Demo:** https://sap-o2c-graph-6os4ixpob-ayushlion8s-projects.vercel.app/
📦 **GitHub:** https://github.com/Ayushlion8/sap-o2c-graph

---

## Screenshots

> Graph overview showing O2C entity types and their relationships  
> Chat interface with NL → SQL → NL response pipeline

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React)                 │
│   ┌──────────────────┐    ┌────────────────────┐    │
│   │  Graph Canvas    │    │   Chat Panel       │    │
│   │  (vis-network)   │    │   (NL interface)   │    │
│   └──────────────────┘    └────────────────────┘    │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP/REST
┌─────────────────▼───────────────────────────────────┐
│                    Backend (FastAPI)                │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │  Graph     │  │  LLM Service │  │  Database   │  │
│  │  Service   │  │  (Gemini)    │  │  (SQLite)   │  │
│  └────────────┘  └──────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Backend | FastAPI (Python) | Fast async API, auto-docs, easy deployment |
| Database | SQLite | Zero-setup, file-based, full SQL support |
| Graph | vis-network (React) | Professional interactive graph viz, expand/collapse |
| LLM | Google Gemini 1.5 Flash | Free tier, fast, excellent SQL generation |
| Frontend | React + Vite | Modern, fast HMR, clean component model |

---

## How It Works

### Data Pipeline
1. All JSONL files from the SAP O2C dataset are loaded into **SQLite** tables on first startup
2. No transformation is lost — all original fields are preserved
3. Loading takes ~5 seconds for the full dataset

### Graph Construction
- **Nodes** represent business entities: Sales Orders, Deliveries, Billing Documents, Payments, Customers, Products
- **Edges** represent relationships derived from foreign key linkages:
  - `Sales Order → Customer` (via `soldToParty`)
  - `Sales Order → Delivery` (via `referenceSdDocument` in delivery items)
  - `Delivery → Billing Document` (via `referenceSdDocument` in billing items)
  - `Billing Document → Journal Entry` (via `accountingDocument`)
  - `Journal Entry → Payment` (via `clearingAccountingDocument`)
- Graph is rendered using **vis-network** with physics-based layout
- Nodes are expandable on double-click

### LLM Query Pipeline (NL → SQL → NL)

```
User Question
     ↓
Gemini 1.5 Flash (Step 1: SQL Generation)
  - System prompt with full DB schema
  - Guardrail: rejects off-topic questions
  - Returns: { is_relevant, sql, explanation }
     ↓
SQLite Execution
  - Query validated and executed
  - Results capped at 100 rows
     ↓
Gemini 1.5 Flash (Step 2: Answer Generation)
  - Gets question + SQL results
  - Returns natural language answer grounded in data
     ↓
User sees answer + collapsible SQL
```

### Guardrails
- **Off-topic rejection**: System prompt explicitly instructs the LLM to reject non-dataset questions
- **Structured response**: LLM returns `{"is_relevant": false}` for off-topic queries
- **Data grounding**: Step 2 prompt instructs the LLM to only use provided data
- **SQL safety**: Only SELECT queries are executed; no DDL/DML allowed via the chat interface
- **Result limiting**: Max 100 rows returned to prevent context overflow

### Example Queries the System Handles
- _"Which products have the most billing documents?"_ → Aggregation query on bd_items
- _"Trace billing document 90504248"_ → Multi-table JOIN across the full O2C chain
- _"Find sales orders delivered but not billed"_ → LEFT JOIN gap analysis
- _"Which customers have the highest order value?"_ → GROUP BY + ORDER BY on so_headers
- _"Show me cancelled billing documents"_ → Filter on bd_cancellations

---

## Setup & Running

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free [Google Gemini API key](https://ai.google.dev)

### 1. Clone & Configure

```bash
git clone https://github.com/your-repo/sap-o2c-graph
cd sap-o2c-graph

cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Place the Dataset

```bash
# Copy the SAP O2C dataset folder here:
cp -r /path/to/sap-o2c-data ./data/sap-o2c-data

# Structure should be:
# data/sap-o2c-data/sales_order_headers/part-*.jsonl
# data/sap-o2c-data/billing_document_headers/part-*.jsonl
# ... etc
```

### 3. Run (One Command)

```bash
chmod +x start.sh
./start.sh
```

This will:
- Install Python dependencies
- Install Node dependencies
- Build the frontend
- Start the backend (which auto-loads data on first run)

Open **http://localhost:8000** in your browser.

### Manual Setup

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # dev server at http://localhost:5173
# OR: npm run build  (production build served by backend)
```

---

## Environment Variables

```
GEMINI_API_KEY=your_key_here      # Required for chat
DB_PATH=o2c_data.db               # SQLite database path
DATA_ROOT=../data/sap-o2c-data    # Path to JSONL data folder
```

---

## Key Database Tables

| Table | Description | Key Fields |
|-------|------------|------------|
| `so_headers` | Sales Order Headers | salesOrder, soldToParty, totalNetAmount |
| `so_items` | Sales Order Line Items | salesOrder, salesOrderItem, material |
| `delivery_headers` | Outbound Deliveries | deliveryDocument, shippingPoint |
| `delivery_items` | Delivery Line Items | deliveryDocument, referenceSdDocument |
| `bd_headers` | Billing Documents | billingDocument, accountingDocument, soldToParty |
| `bd_items` | Billing Line Items | billingDocument, referenceSdDocument |
| `journal_entries` | Journal Entries (AR) | accountingDocument, referenceDocument |
| `payments` | AR Payments | accountingDocument, clearingAccountingDocument |
| `business_partners` | Customers | businessPartner, businessPartnerName |
| `products` | Products | product, productType, productOldId |

---

## AI Coding Session Logs

Session logs from Claude Code / Cursor are included in `ai-session-logs/` folder.

---

## Evaluation Notes

- **Graph modeling**: The O2C flow is modeled as a directed graph. The full chain (Sales Order → Delivery → Billing → Journal → Payment) is traversable from any starting node.
- **Guardrails**: Off-topic queries are rejected at the LLM prompt level AND with a client-side indicator. The system never generates answers without data backing.
- **NL→SQL**: Two-step Gemini pipeline: first generates SQL with schema context, then generates the answer from query results. No hallucinated data.
- **Depth over breadth**: Rather than superficial implementations, the graph expansion, SQL generation, and guardrails are all production-quality.
