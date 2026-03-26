import sqlite3
import json
from typing import Any, Optional


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=OFF")
        return conn

    def execute_query(self, sql: str, params=()) -> list[dict]:
        """Execute a SELECT query and return rows as dicts."""
        conn = self.get_conn()
        try:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_table_names(self) -> list[str]:
        rows = self.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [r["name"] for r in rows]

    def get_schema_summary(self) -> str:
        """Returns a human-readable schema summary for LLM context."""
        conn = sqlite3.connect(self.db_path)
        tables = self.get_table_names()
        lines = []

        table_descriptions = {
            "so_headers": "Sales Order Headers - one row per sales order",
            "so_items": "Sales Order Items - line items within a sales order",
            "so_schedule_lines": "Sales Order Schedule Lines - delivery schedule per item",
            "delivery_headers": "Outbound Delivery Headers - one row per delivery",
            "delivery_items": "Delivery Items - items within a delivery",
            "bd_headers": "Billing Document Headers - invoices, one row per billing doc",
            "bd_items": "Billing Document Items - line items within a billing document",
            "bd_cancellations": "Billing Document Cancellations - cancelled billing documents",
            "journal_entries": "Journal Entry Items (Accounts Receivable) - accounting entries",
            "payments": "Payments / Accounts Receivable - payment records",
            "business_partners": "Business Partners / Customers",
            "bp_addresses": "Business Partner Addresses",
            "products": "Product master data",
            "product_descriptions": "Product descriptions by language",
            "plants": "Plant master data",
            "product_plants": "Product-plant assignments",
            "product_storage": "Product storage locations",
            "cust_company": "Customer company code assignments",
            "cust_sales_area": "Customer sales area assignments",
        }

        key_relationships = """
KEY RELATIONSHIPS (use these JOINs):
- so_items.salesOrder = so_headers.salesOrder
- so_headers.soldToParty = business_partners.businessPartner
- delivery_items.referenceSdDocument = so_headers.salesOrder  (delivery references sales order)
- delivery_headers.deliveryDocument = delivery_items.deliveryDocument
- bd_items.referenceSdDocument = delivery_headers.deliveryDocument  (billing references delivery)
- bd_headers.billingDocument = bd_items.billingDocument
- bd_headers.accountingDocument = journal_entries.accountingDocument
- journal_entries.clearingAccountingDocument = payments.accountingDocument
- bd_headers.soldToParty = business_partners.businessPartner
- so_items.material = products.product
- bd_items.material = products.product
"""

        for t in tables:
            cursor = conn.execute(f'PRAGMA table_info("{t}")')
            cols = [row[1] for row in cursor.fetchall()]
            desc = table_descriptions.get(t, "")
            lines.append(f"Table: {t}")
            if desc:
                lines.append(f"  Description: {desc}")
            lines.append(f"  Columns: {', '.join(cols)}")
            lines.append("")

        conn.close()
        return "\n".join(lines) + key_relationships

    def get_entity_counts(self) -> dict:
        """Return record counts for main entity tables."""
        main_tables = [
            "so_headers", "delivery_headers", "bd_headers",
            "journal_entries", "payments", "business_partners", "products", "plants"
        ]
        counts = {}
        for t in main_tables:
            try:
                rows = self.execute_query(f'SELECT COUNT(*) as cnt FROM "{t}"')
                counts[t] = rows[0]["cnt"] if rows else 0
            except Exception:
                counts[t] = 0
        return counts
