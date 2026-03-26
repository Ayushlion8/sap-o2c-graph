import sqlite3
from typing import Optional
import json

# Node type colors
NODE_COLORS = {
    "SalesOrder":       {"background": "#3B82F6", "border": "#1D4ED8", "highlight": {"background": "#60A5FA", "border": "#2563EB"}},
    "Delivery":         {"background": "#10B981", "border": "#059669", "highlight": {"background": "#34D399", "border": "#10B981"}},
    "BillingDocument":  {"background": "#F59E0B", "border": "#D97706", "highlight": {"background": "#FCD34D", "border": "#F59E0B"}},
    "JournalEntry":     {"background": "#8B5CF6", "border": "#7C3AED", "highlight": {"background": "#A78BFA", "border": "#8B5CF6"}},
    "Payment":          {"background": "#EF4444", "border": "#DC2626", "highlight": {"background": "#FCA5A5", "border": "#EF4444"}},
    "Customer":         {"background": "#F97316", "border": "#EA580C", "highlight": {"background": "#FDBA74", "border": "#F97316"}},
    "Product":          {"background": "#06B6D4", "border": "#0891B2", "highlight": {"background": "#67E8F9", "border": "#06B6D4"}},
    "Plant":            {"background": "#6B7280", "border": "#4B5563", "highlight": {"background": "#9CA3AF", "border": "#6B7280"}},
}

NODE_SHAPES = {
    "SalesOrder": "box",
    "Delivery": "ellipse",
    "BillingDocument": "diamond",
    "JournalEntry": "hexagon",
    "Payment": "star",
    "Customer": "database",
    "Product": "box",
    "Plant": "triangleDown",
}


def make_node(node_id: str, label: str, node_type: str, title: str = "", data: dict = None):
    color = NODE_COLORS.get(node_type, {"background": "#64748B", "border": "#475569"})
    return {
        "id": node_id,
        "label": label,
        "group": node_type,
        "color": color,
        "shape": NODE_SHAPES.get(node_type, "ellipse"),
        "title": title,
        "nodeType": node_type,
        "data": data or {},
        "font": {"color": "#FFFFFF", "size": 12},
    }


def make_edge(from_id: str, to_id: str, label: str, edge_id: str = None):
    return {
        "id": edge_id or f"{from_id}__{to_id}__{label}",
        "from": from_id,
        "to": to_id,
        "label": label,
        "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
        "color": {"color": "#94A3B8", "highlight": "#CBD5E1"},
        "font": {"color": "#94A3B8", "size": 10, "align": "middle"},
        "smooth": {"type": "curvedCW", "roundness": 0.1},
    }


class GraphService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _q(self, sql: str, params=()):
        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_overview_graph(self) -> dict:
        """Returns a high-level O2C flow graph showing entity types with counts."""
        nodes = []
        edges = []

        # Entity type summary nodes
        entity_configs = [
            ("Customer",        "so_headers",       "soldToParty",      "👤 Customers"),
            ("SalesOrder",      "so_headers",        "salesOrder",       "📋 Sales Orders"),
            ("Delivery",        "delivery_headers",  "deliveryDocument", "🚚 Deliveries"),
            ("BillingDocument", "bd_headers",        "billingDocument",  "🧾 Billing Docs"),
            ("JournalEntry",    "journal_entries",   "accountingDocument","📒 Journal Entries"),
            ("Payment",         "payments",          "accountingDocument","💰 Payments"),
        ]

        for node_type, table, id_col, label_prefix in entity_configs:
            try:
                rows = self._q(f'SELECT COUNT(DISTINCT "{id_col}") as cnt FROM "{table}"')
                cnt = rows[0]["cnt"] if rows else 0
            except Exception:
                cnt = 0

            nid = f"type_{node_type}"
            nodes.append(make_node(
                node_id=nid,
                label=f"{label_prefix}\n({cnt})",
                node_type=node_type,
                title=f"<b>{node_type}</b><br/>Total: {cnt} records<br/><i>Click to explore</i>",
                data={"entityType": node_type, "count": cnt, "isTypeNode": True}
            ))

        # O2C flow edges
        flow = [
            ("type_Customer",        "type_SalesOrder",      "places"),
            ("type_SalesOrder",      "type_Delivery",        "fulfilled by"),
            ("type_Delivery",        "type_BillingDocument", "billed as"),
            ("type_BillingDocument", "type_JournalEntry",    "posted to"),
            ("type_JournalEntry",    "type_Payment",         "cleared by"),
        ]
        for f, t, lbl in flow:
            edges.append(make_edge(f, t, lbl))

        return {"nodes": nodes, "edges": edges, "layout": "flow"}

    def expand_entity_type(self, entity_type: str, limit: int = 30) -> dict:
        """Expand an entity type node to show actual records."""
        nodes = []
        edges = []

        type_node_id = f"type_{entity_type}"

        if entity_type == "SalesOrder":
            rows = self._q(f'''
                SELECT h.salesOrder, h.soldToParty, h.totalNetAmount, h.creationDate,
                       h.overallDeliveryStatus, h.overallOrdReltdBillgStatus,
                       bp.businessPartnerName
                FROM so_headers h
                LEFT JOIN business_partners bp ON h.soldToParty = bp.businessPartner
                LIMIT {limit}
            ''')
            for r in rows:
                nid = f"SO_{r['salesOrder']}"
                amount = f"₹{float(r['totalNetAmount'] or 0):,.0f}" if r['totalNetAmount'] else "N/A"
                nodes.append(make_node(
                    nid, f"SO {r['salesOrder']}\n{amount}",
                    "SalesOrder",
                    title=f"<b>Sales Order: {r['salesOrder']}</b><br/>Customer: {r.get('businessPartnerName','')}<br/>Amount: {amount}<br/>Del Status: {r.get('overallDeliveryStatus','')}<br/>Bill Status: {r.get('overallOrdReltdBillgStatus','')}",
                    data=dict(r)
                ))
                edges.append(make_edge(type_node_id, nid, ""))

        elif entity_type == "Delivery":
            rows = self._q(f'''
                SELECT d.deliveryDocument, d.creationDate, d.shippingPoint,
                       d.overallGoodsMovementStatus, d.overallPickingStatus
                FROM delivery_headers d LIMIT {limit}
            ''')
            for r in rows:
                nid = f"DEL_{r['deliveryDocument']}"
                nodes.append(make_node(
                    nid, f"DEL {r['deliveryDocument']}",
                    "Delivery",
                    title=f"<b>Delivery: {r['deliveryDocument']}</b><br/>Goods Movement: {r.get('overallGoodsMovementStatus','')}<br/>Picking: {r.get('overallPickingStatus','')}",
                    data=dict(r)
                ))
                edges.append(make_edge(type_node_id, nid, ""))

        elif entity_type == "BillingDocument":
            rows = self._q(f'''
                SELECT b.billingDocument, b.billingDocumentType, b.totalNetAmount,
                       b.creationDate, b.billingDocumentIsCancelled, b.soldToParty,
                       bp.businessPartnerName
                FROM bd_headers b
                LEFT JOIN business_partners bp ON b.soldToParty = bp.businessPartner
                WHERE b.billingDocumentIsCancelled != 'True'
                LIMIT {limit}
            ''')
            for r in rows:
                nid = f"BD_{r['billingDocument']}"
                amount = f"₹{float(r['totalNetAmount'] or 0):,.0f}" if r['totalNetAmount'] else "N/A"
                nodes.append(make_node(
                    nid, f"BD {r['billingDocument']}\n{amount}",
                    "BillingDocument",
                    title=f"<b>Billing Doc: {r['billingDocument']}</b><br/>Type: {r.get('billingDocumentType','')}<br/>Amount: {amount}<br/>Customer: {r.get('businessPartnerName','')}",
                    data=dict(r)
                ))
                edges.append(make_edge(type_node_id, nid, ""))

        elif entity_type == "JournalEntry":
            rows = self._q(f'''
                SELECT DISTINCT accountingDocument, companyCode, glAccount,
                       amountInTransactionCurrency, postingDate, referenceDocument
                FROM journal_entries LIMIT {limit}
            ''')
            for r in rows:
                nid = f"JE_{r['accountingDocument']}"
                amount = f"₹{float(r['amountInTransactionCurrency'] or 0):,.0f}" if r['amountInTransactionCurrency'] else "N/A"
                nodes.append(make_node(
                    nid, f"JE {r['accountingDocument']}\n{amount}",
                    "JournalEntry",
                    title=f"<b>Journal Entry: {r['accountingDocument']}</b><br/>GL: {r.get('glAccount','')}<br/>Amount: {amount}<br/>Ref: {r.get('referenceDocument','')}",
                    data=dict(r)
                ))
                edges.append(make_edge(type_node_id, nid, ""))

        elif entity_type == "Payment":
            rows = self._q(f'''
                SELECT DISTINCT accountingDocument, customer, amountInTransactionCurrency,
                       clearingDate, clearingAccountingDocument
                FROM payments LIMIT {limit}
            ''')
            for r in rows:
                nid = f"PAY_{r['accountingDocument']}"
                amount = f"₹{float(r['amountInTransactionCurrency'] or 0):,.0f}" if r['amountInTransactionCurrency'] else "N/A"
                nodes.append(make_node(
                    nid, f"PAY {r['accountingDocument']}\n{amount}",
                    "Payment",
                    title=f"<b>Payment: {r['accountingDocument']}</b><br/>Customer: {r.get('customer','')}<br/>Amount: {amount}<br/>Cleared: {r.get('clearingDate','')}",
                    data=dict(r)
                ))
                edges.append(make_edge(type_node_id, nid, ""))

        elif entity_type == "Customer":
            rows = self._q(f'''
                SELECT businessPartner, businessPartnerName, businessPartnerCategory,
                       creationDate, businessPartnerIsBlocked
                FROM business_partners LIMIT {limit}
            ''')
            for r in rows:
                nid = f"CUST_{r['businessPartner']}"
                nodes.append(make_node(
                    nid, f"👤 {r.get('businessPartnerName', r['businessPartner'])}",
                    "Customer",
                    title=f"<b>Customer: {r['businessPartner']}</b><br/>Name: {r.get('businessPartnerName','')}<br/>Created: {r.get('creationDate','')}",
                    data=dict(r)
                ))
                edges.append(make_edge(type_node_id, nid, ""))

        return {"nodes": nodes, "edges": edges}

    def get_node_neighborhood(self, node_type: str, node_id: str) -> dict:
        """Get a node and all its direct connections."""
        nodes = []
        edges = []

        if node_type == "SalesOrder":
            # Get the sales order
            so_rows = self._q('SELECT * FROM so_headers WHERE salesOrder = ?', (node_id,))
            if not so_rows:
                return {"nodes": [], "edges": []}
            r = so_rows[0]
            amount = f"₹{float(r['totalNetAmount'] or 0):,.0f}" if r.get('totalNetAmount') else "N/A"
            so_nid = f"SO_{node_id}"
            nodes.append(make_node(so_nid, f"SO {node_id}\n{amount}", "SalesOrder",
                title=f"<b>Sales Order {node_id}</b><br/>Amount: {amount}", data=r))

            # Customer
            cust_rows = self._q('SELECT * FROM business_partners WHERE businessPartner = ?', (r.get('soldToParty'),))
            if cust_rows:
                cr = cust_rows[0]
                cid = f"CUST_{cr['businessPartner']}"
                nodes.append(make_node(cid, f"👤 {cr.get('businessPartnerName', cr['businessPartner'])}", "Customer",
                    title=f"<b>Customer: {cr['businessPartner']}</b><br/>{cr.get('businessPartnerName','')}", data=cr))
                edges.append(make_edge(cid, so_nid, "places"))

            # SO Items
            item_rows = self._q('SELECT * FROM so_items WHERE salesOrder = ?', (node_id,))
            for item in item_rows[:10]:
                item_nid = f"SOI_{node_id}_{item['salesOrderItem']}"
                nodes.append(make_node(item_nid,
                    f"Item {item['salesOrderItem']}\n{item.get('material','')}",
                    "SalesOrder",
                    title=f"<b>SO Item {item['salesOrderItem']}</b><br/>Material: {item.get('material','')}<br/>Qty: {item.get('requestedQuantity','')}",
                    data=item))
                edges.append(make_edge(so_nid, item_nid, "has item"))

                # Product
                prod_rows = self._q('SELECT * FROM products WHERE product = ?', (item.get('material'),))
                if prod_rows:
                    pr = prod_rows[0]
                    pid = f"PROD_{pr['product']}"
                    if not any(n['id'] == pid for n in nodes):
                        nodes.append(make_node(pid, f"📦 {pr.get('productOldId', pr['product'])}", "Product",
                            title=f"<b>Product: {pr['product']}</b><br/>Type: {pr.get('productType','')}", data=pr))
                    edges.append(make_edge(item_nid, pid, "material"))

            # Deliveries referencing this SO
            del_rows = self._q('''
                SELECT DISTINCT dh.* FROM delivery_headers dh
                JOIN delivery_items di ON dh.deliveryDocument = di.deliveryDocument
                WHERE di.referenceSdDocument = ?
            ''', (node_id,))
            for dr in del_rows[:5]:
                did = f"DEL_{dr['deliveryDocument']}"
                nodes.append(make_node(did, f"DEL {dr['deliveryDocument']}", "Delivery",
                    title=f"<b>Delivery: {dr['deliveryDocument']}</b>", data=dr))
                edges.append(make_edge(so_nid, did, "fulfilled by"))

                # Billing docs referencing this delivery
                bd_rows = self._q('''
                    SELECT DISTINCT bh.* FROM bd_headers bh
                    JOIN bd_items bi ON bh.billingDocument = bi.billingDocument
                    WHERE bi.referenceSdDocument = ?
                ''', (dr['deliveryDocument'],))
                for br in bd_rows[:5]:
                    bid = f"BD_{br['billingDocument']}"
                    if not any(n['id'] == bid for n in nodes):
                        amount2 = f"₹{float(br['totalNetAmount'] or 0):,.0f}" if br.get('totalNetAmount') else "N/A"
                        nodes.append(make_node(bid, f"BD {br['billingDocument']}\n{amount2}", "BillingDocument",
                            title=f"<b>Billing Doc: {br['billingDocument']}</b><br/>Amount: {amount2}", data=br))
                    edges.append(make_edge(did, bid, "billed as"))

                    # Journal entries
                    je_rows = self._q('SELECT DISTINCT accountingDocument, amountInTransactionCurrency, referenceDocument FROM journal_entries WHERE accountingDocument = ?',
                        (br.get('accountingDocument'),))
                    for jr in je_rows[:3]:
                        jid = f"JE_{jr['accountingDocument']}"
                        if not any(n['id'] == jid for n in nodes):
                            nodes.append(make_node(jid, f"JE {jr['accountingDocument']}", "JournalEntry",
                                title=f"<b>Journal Entry: {jr['accountingDocument']}</b>", data=jr))
                        edges.append(make_edge(bid, jid, "posted to"))

        elif node_type == "BillingDocument":
            bd_rows = self._q('SELECT * FROM bd_headers WHERE billingDocument = ?', (node_id,))
            if not bd_rows:
                return {"nodes": [], "edges": []}
            r = bd_rows[0]
            amount = f"₹{float(r['totalNetAmount'] or 0):,.0f}" if r.get('totalNetAmount') else "N/A"
            bid = f"BD_{node_id}"
            nodes.append(make_node(bid, f"BD {node_id}\n{amount}", "BillingDocument",
                title=f"<b>Billing Doc {node_id}</b><br/>Amount: {amount}", data=r))

            # Customer
            cust_rows = self._q('SELECT * FROM business_partners WHERE businessPartner = ?', (r.get('soldToParty'),))
            if cust_rows:
                cr = cust_rows[0]
                cid = f"CUST_{cr['businessPartner']}"
                nodes.append(make_node(cid, f"👤 {cr.get('businessPartnerName', cr['businessPartner'])}", "Customer",
                    title=f"<b>Customer: {cr['businessPartner']}</b>", data=cr))
                edges.append(make_edge(cid, bid, "billed to"))

            # BD Items and linked delivery/SO
            bd_item_rows = self._q('SELECT * FROM bd_items WHERE billingDocument = ?', (node_id,))
            for item in bd_item_rows[:10]:
                item_nid = f"BDI_{node_id}_{item['billingDocumentItem']}"
                nodes.append(make_node(item_nid,
                    f"Item {item['billingDocumentItem']}\n{item.get('material','')}",
                    "BillingDocument",
                    title=f"<b>BD Item {item['billingDocumentItem']}</b><br/>Material: {item.get('material','')}<br/>Qty: {item.get('billingQuantity','')}<br/>Ref: {item.get('referenceSdDocument','')}",
                    data=item))
                edges.append(make_edge(bid, item_nid, "has item"))

                # Delivery
                ref_del = item.get('referenceSdDocument')
                if ref_del:
                    del_rows = self._q('SELECT * FROM delivery_headers WHERE deliveryDocument = ?', (ref_del,))
                    if del_rows:
                        dr = del_rows[0]
                        did = f"DEL_{dr['deliveryDocument']}"
                        if not any(n['id'] == did for n in nodes):
                            nodes.append(make_node(did, f"DEL {dr['deliveryDocument']}", "Delivery",
                                title=f"<b>Delivery: {dr['deliveryDocument']}</b>", data=dr))
                        edges.append(make_edge(did, item_nid, "fulfilled by"))

            # Journal entries
            je_rows = self._q('SELECT DISTINCT accountingDocument, amountInTransactionCurrency FROM journal_entries WHERE accountingDocument = ?',
                (r.get('accountingDocument'),))
            for jr in je_rows[:3]:
                jid = f"JE_{jr['accountingDocument']}"
                if not any(n['id'] == jid for n in nodes):
                    nodes.append(make_node(jid, f"JE {jr['accountingDocument']}", "JournalEntry",
                        title=f"<b>Journal Entry: {jr['accountingDocument']}</b>", data=jr))
                edges.append(make_edge(bid, jid, "posted to"))

        elif node_type == "Customer":
            cust_rows = self._q('SELECT * FROM business_partners WHERE businessPartner = ?', (node_id,))
            if not cust_rows:
                return {"nodes": [], "edges": []}
            r = cust_rows[0]
            cid = f"CUST_{node_id}"
            nodes.append(make_node(cid, f"👤 {r.get('businessPartnerName', node_id)}", "Customer",
                title=f"<b>Customer: {node_id}</b><br/>{r.get('businessPartnerName','')}", data=r))

            # Sales Orders
            so_rows = self._q('SELECT salesOrder, totalNetAmount, creationDate, overallDeliveryStatus FROM so_headers WHERE soldToParty = ?', (node_id,))
            for sr in so_rows[:10]:
                so_nid = f"SO_{sr['salesOrder']}"
                amount = f"₹{float(sr['totalNetAmount'] or 0):,.0f}" if sr.get('totalNetAmount') else "N/A"
                nodes.append(make_node(so_nid, f"SO {sr['salesOrder']}\n{amount}", "SalesOrder",
                    title=f"<b>Sales Order: {sr['salesOrder']}</b><br/>Amount: {amount}", data=sr))
                edges.append(make_edge(cid, so_nid, "places"))

            # Billing Docs
            bd_rows = self._q('SELECT billingDocument, totalNetAmount FROM bd_headers WHERE soldToParty = ?', (node_id,))
            for br in bd_rows[:5]:
                bid2 = f"BD_{br['billingDocument']}"
                amount = f"₹{float(br['totalNetAmount'] or 0):,.0f}" if br.get('totalNetAmount') else "N/A"
                nodes.append(make_node(bid2, f"BD {br['billingDocument']}\n{amount}", "BillingDocument",
                    title=f"<b>Billing Doc: {br['billingDocument']}</b><br/>Amount: {amount}", data=br))
                edges.append(make_edge(cid, bid2, "billed"))

        return {"nodes": nodes, "edges": edges}

    def get_full_o2c_flow(self, sales_order: str) -> dict:
        """Get full O2C flow for a given sales order."""
        result = self.get_node_neighborhood("SalesOrder", sales_order)
        result["focusNode"] = f"SO_{sales_order}"
        return result
