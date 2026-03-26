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

IMPORTANT:
If a question requires a specific identifier (e.g., billing document, sales order) 
and none is provided, respond EXACTLY with:
{"is_relevant": false, "reason": "missing_identifier"}

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
- LIMIT results to 100 rows max unless user asks for all
"""

ANSWER_SYSTEM_PROMPT = """You are an SAP Order-to-Cash data analyst. 
Given a user question and SQL query results from the database, provide a clear, concise, data-backed answer.

RULES:
- Base your answer ONLY on the data provided
- Be specific — mention actual values
- If the result is empty, say so clearly
- Keep answers short (2-3 sentences)
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
        system = GUARDRAIL_SYSTEM_PROMPT.replace("{schema}", self.schema_summary)

        raw = self._call_gemini(system, user_question, temperature=0.05)

        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            return {"is_relevant": False, "reason": "parse_error", "raw": raw}

    def generate_answer(self, user_question: str, sql: str, results: list[dict]) -> str:
        # ✅ EMPTY RESULT FIX
        if not results:
            return "No results found for this query."

        # ✅ LIMIT DATA
        limited_results = results[:10]

        formatted_rows = "\n".join([
            ", ".join(f"{k}: {v}" for k, v in row.items())
            for row in limited_results
        ])

        user_msg = f"""Question: {user_question}

SQL Query Used:
{sql}

Top Results:
{formatted_rows}

Give a concise answer."""

        return self._call_gemini(ANSWER_SYSTEM_PROMPT, user_msg, temperature=0.3)

    def chat(self, user_question: str, db) -> dict:
        translation = self.translate_to_sql(user_question)

        # ✅ HANDLE NON-RELEVANT CASES
        if not translation.get("is_relevant", True):
            reason = translation.get("reason", "off_topic")

            if reason == "off_topic":
                return {
                    "answer": "This system answers only SAP O2C dataset questions.",
                    "sql": None,
                    "results": [],
                    "is_relevant": False,
                }

            if reason == "missing_identifier":
                return {
                    "answer": "Please provide a specific ID (e.g., billing document number like 90504248).",
                    "sql": None,
                    "results": [],
                    "is_relevant": True,
                }

            return {
                "answer": "I had trouble processing that query. Please try rephrasing.",
                "sql": None,
                "results": [],
                "is_relevant": False,
            }

        sql = translation.get("sql", "")

        # ✅ SMART FALLBACK FOR AMBIGUOUS QUERIES
        if not sql:
            q = user_question.lower()

            if "billing document" in q:
                return {
                    "answer": "Please provide a billing document ID (e.g., 90504248) to trace its flow.",
                    "sql": None,
                    "results": [],
                    "is_relevant": True,
                }

            if "sales order" in q:
                return {
                    "answer": "Please provide a sales order ID to proceed.",
                    "sql": None,
                    "results": [],
                    "is_relevant": True,
                }

            return {
                "answer": "I couldn't generate a query for that question. Please rephrase.",
                "sql": None,
                "results": [],
                "is_relevant": True,
            }

        # Execute SQL
        try:
            results = db.execute_query(sql)
        except Exception as e:
            return {
                "answer": f"The query encountered an error: {str(e)}.",
                "sql": sql,
                "results": [],
                "is_relevant": True,
                "error": str(e),
            }

        # Generate answer
        try:
            answer = self.generate_answer(user_question, sql, results)
        except:
            answer = f"Found {len(results)} results but couldn't generate a summary."

        return {
            "answer": answer,
            "sql": sql,
            "results": results[:100],
            "row_count": len(results),
            "is_relevant": True,
            "explanation": translation.get("explanation", ""),
        }