import os
import json
import httpx
from typing import Optional


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

GUARDRAIL_SYSTEM_PROMPT = """You are an SAP Order-to-Cash (O2C) data analyst assistant.

CRITICAL RULE: You ONLY answer questions about the SAP Order-to-Cash dataset provided. 
If asked ANYTHING unrelated — general knowledge, math problems, coding help, creative writing, opinions, 
current events, or anything outside this dataset — respond EXACTLY with:
{"is_relevant": false, "reason": "off_topic"}

DATASET CONTEXT:
This is an SAP O2C (Order-to-Cash) system containing: Sales Orders, Deliveries, Billing Documents, 
Journal Entries, Payments, Business Partners/Customers, and Products.

DATABASE SCHEMA:
{schema}

YOUR TASK:
When given a user question about this dataset:
1. Check if it's about the O2C dataset → if NOT, return {{"is_relevant": false, "reason": "off_topic"}}
2. If YES, write a SQLite SQL query to answer it
3. Return ONLY valid JSON (no markdown, no code blocks):

{{
  "is_relevant": true,
  "sql": "SELECT ...",
  "explanation": "Brief explanation of what this query does"
}}

SQL RULES:
- Use SQLite syntax only
- Always use table aliases for clarity
- For date comparisons use: DATE(column) or strftime()
- String values are stored as TEXT — use LIKE for partial matches
- Boolean fields stored as text 'True'/'False'
- Numbers stored as TEXT — cast with CAST(col AS REAL) for math
- Nested JSON (like creationTime) stored as JSON string text
- LIMIT results to 100 rows max unless user asks for all
- For "broken flow" queries: use LEFT JOINs and check for NULL on expected joins

EXAMPLE QUERIES:
Q: "Which products have the most billing documents?"
SQL: SELECT bi.material, COUNT(DISTINCT bi.billingDocument) as bill_count 
     FROM bd_items bi GROUP BY bi.material ORDER BY bill_count DESC LIMIT 10

Q: "Trace billing document 90504248"  
SQL: SELECT bh.billingDocument, bh.totalNetAmount, di.referenceSdDocument as delivery,
     dh.deliveryDocument, sh.salesOrder, sh.soldToParty, je.accountingDocument
     FROM bd_headers bh
     LEFT JOIN bd_items bi ON bh.billingDocument = bi.billingDocument
     LEFT JOIN delivery_headers dh ON bi.referenceSdDocument = dh.deliveryDocument
     LEFT JOIN delivery_items di ON dh.deliveryDocument = di.deliveryDocument
     LEFT JOIN so_headers sh ON di.referenceSdDocument = sh.salesOrder
     LEFT JOIN journal_entries je ON bh.accountingDocument = je.accountingDocument
     WHERE bh.billingDocument = '90504248' LIMIT 1

Q: "Find sales orders delivered but not billed"
SQL: SELECT sh.salesOrder, sh.soldToParty, sh.totalNetAmount
     FROM so_headers sh
     JOIN delivery_items di ON di.referenceSdDocument = sh.salesOrder
     LEFT JOIN bd_items bi ON bi.referenceSdDocument = (
         SELECT deliveryDocument FROM delivery_items WHERE referenceSdDocument = sh.salesOrder LIMIT 1
     )
     WHERE bi.billingDocument IS NULL
     GROUP BY sh.salesOrder
"""

ANSWER_SYSTEM_PROMPT = """You are an SAP Order-to-Cash data analyst. 
Given a user question and SQL query results from the database, provide a clear, concise, data-backed answer.

RULES:
- Base your answer ONLY on the data provided
- Be specific — mention actual values, IDs, amounts from the results
- Format numbers nicely (e.g., ₹1,234.56 for INR amounts)
- If the result is empty, say so clearly
- Keep answers focused and professional (2-5 sentences typically)
- Do NOT make up data not in the results
- Do NOT answer questions unrelated to the dataset

If the question is about order status, use this legend:
- overallDeliveryStatus: A=Not Delivered, B=Partially Delivered, C=Fully Delivered
- overallOrdReltdBillgStatus: A=Not Billed, B=Partially Billed, C=Fully Billed, empty=Not yet relevant
"""


class LLMService:
    def __init__(self, api_key: str, schema_summary: str):
        self.api_key = api_key
        self.schema_summary = schema_summary

    def _call_gemini(self, system_prompt: str, user_message: str, temperature: float = 0.1) -> str:
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_message}], "role": "user"}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 1024,
            }
        }
        headers = {"Content-Type": "application/json"}
        url = f"{GEMINI_API_URL}?key={self.api_key}"

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in Gemini response")
        return candidates[0]["content"]["parts"][0]["text"].strip()

    def translate_to_sql(self, user_question: str) -> dict:
        """Translate natural language to SQL. Returns dict with is_relevant, sql, explanation."""
        system = GUARDRAIL_SYSTEM_PROMPT.replace("{schema}", self.schema_summary)

        raw = self._call_gemini(system, user_question, temperature=0.05)

        # Strip markdown code blocks if present
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            return {"is_relevant": False, "reason": "parse_error", "raw": raw}

    def generate_answer(self, user_question: str, sql: str, results: list[dict]) -> str:
        """Generate natural language answer from SQL results."""
        results_str = json.dumps(results[:50], indent=2, default=str)  # limit to 50 rows in prompt
        user_msg = f"""Question: {user_question}

SQL Query Used:
{sql}

Query Results ({len(results)} rows):
{results_str}

Please provide a clear, concise answer to the question based on these results."""

        return self._call_gemini(ANSWER_SYSTEM_PROMPT, user_msg, temperature=0.3)

    def chat(self, user_question: str, db) -> dict:
        """Full chat pipeline: NL → SQL → Execute → NL Answer."""
        # Step 1: Translate to SQL
        translation = self.translate_to_sql(user_question)

        if not translation.get("is_relevant", True):
            reason = translation.get("reason", "off_topic")
            if reason == "off_topic":
                return {
                    "answer": "This system is designed to answer questions related to the SAP Order-to-Cash dataset only. Please ask questions about sales orders, deliveries, billing documents, payments, customers, or products.",
                    "sql": None,
                    "results": [],
                    "is_relevant": False,
                }
            else:
                return {
                    "answer": "I had trouble processing that query. Please try rephrasing your question.",
                    "sql": None,
                    "results": [],
                    "is_relevant": False,
                }

        sql = translation.get("sql", "")
        if not sql:
            return {
                "answer": "I couldn't generate a query for that question. Please try rephrasing.",
                "sql": None,
                "results": [],
                "is_relevant": True,
            }

        # Step 2: Execute SQL
        try:
            results = db.execute_query(sql)
        except Exception as e:
            return {
                "answer": f"The query encountered an error: {str(e)}. Please try a different question.",
                "sql": sql,
                "results": [],
                "is_relevant": True,
                "error": str(e),
            }

        # Step 3: Generate natural language answer
        try:
            answer = self.generate_answer(user_question, sql, results)
        except Exception as e:
            answer = f"Found {len(results)} results but couldn't generate a summary. Here are the raw results."

        return {
            "answer": answer,
            "sql": sql,
            "results": results[:100],
            "row_count": len(results),
            "is_relevant": True,
            "explanation": translation.get("explanation", ""),
        }
