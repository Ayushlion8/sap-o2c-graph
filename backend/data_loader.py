import json
import sqlite3
import os
import glob
from pathlib import Path

# Map from folder name -> SQLite table name
FOLDER_TABLE_MAP = {
    "billing_document_cancellations": "bd_cancellations",
    "billing_document_headers": "bd_headers",
    "billing_document_items": "bd_items",
    "business_partner_addresses": "bp_addresses",
    "business_partners": "business_partners",
    "customer_company_assignments": "cust_company",
    "customer_sales_area_assignments": "cust_sales_area",
    "journal_entry_items_accounts_receivable": "journal_entries",
    "outbound_delivery_headers": "delivery_headers",
    "outbound_delivery_items": "delivery_items",
    "payments_accounts_receivable": "payments",
    "plants": "plants",
    "product_descriptions": "product_descriptions",
    "product_plants": "product_plants",
    "product_storage_locations": "product_storage",
    "products": "products",
    "sales_order_headers": "so_headers",
    "sales_order_items": "so_items",
    "sales_order_schedule_lines": "so_schedule_lines",
}


def serialize_value(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


def load_jsonl_folder(conn: sqlite3.Connection, table_name: str, folder_path: str) -> int:
    files = sorted(glob.glob(os.path.join(folder_path, "part-*.jsonl")))
    if not files:
        return 0

    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    if not records:
        return 0

    # Collect all columns across all records for a robust schema
    all_columns = []
    seen = set()
    for rec in records[:50]:  # sample first 50 records for columns
        for k in rec.keys():
            if k not in seen:
                all_columns.append(k)
                seen.add(k)

    cols_def = ", ".join([f'"{c}" TEXT' for c in all_columns])
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({cols_def})')

    cols_str = ", ".join([f'"{c}"' for c in all_columns])
    placeholders = ", ".join(["?" for _ in all_columns])
    insert_sql = f'INSERT OR IGNORE INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'

    batch = []
    for rec in records:
        vals = tuple(serialize_value(rec.get(c)) for c in all_columns)
        batch.append(vals)
        if len(batch) >= 500:
            conn.executemany(insert_sql, batch)
            batch = []

    if batch:
        conn.executemany(insert_sql, batch)

    conn.commit()
    return len(records)


def load_all_data(db_path: str, data_root: str) -> dict:
    """Load all JSONL data into SQLite. Returns counts per table."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    counts = {}

    for folder_name, table_name in FOLDER_TABLE_MAP.items():
        folder_path = os.path.join(data_root, folder_name)
        if not os.path.exists(folder_path):
            continue
        n = load_jsonl_folder(conn, table_name, folder_path)
        counts[table_name] = n
        print(f"  Loaded {n} records into {table_name}")

    conn.close()
    return counts


def get_table_schema(db_path: str) -> dict:
    """Returns column names for each table."""
    conn = sqlite3.connect(db_path)
    schema = {}
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    for t in tables:
        cursor = conn.execute(f'PRAGMA table_info("{t}")')
        cols = [row[1] for row in cursor.fetchall()]
        schema[t] = cols
    conn.close()
    return schema
