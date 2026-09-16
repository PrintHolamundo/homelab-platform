import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from db import Database
from paperless_client import PaperlessClient

logger = logging.getLogger("dochat.analyzer")


class DocumentAnalyzer:
    def __init__(
        self,
        paperless: PaperlessClient,
        db: Database,
        gemini_api_key: str,
        gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        gemini_model: str = "gemini-3.5-flash-lite",
    ):
        self.paperless = paperless
        self.db = db
        self.api_key = gemini_api_key
        self.base_url = gemini_base_url.rstrip("/")
        self.model = gemini_model

    async def _call_gemini(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> Optional[str]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content
            except Exception as e:
                logger.error(f"Error calling Gemini: {e}")
                return None

    async def extract_and_cache_financials(self, document_id: int) -> Optional[Dict[str, Any]]:
        # Check cache first (0 tokens)
        cached = self.db.get_financial(document_id)
        if cached:
            return cached

        doc = await self.paperless.get_document(document_id)
        if not doc:
            return None

        content = doc.get("content", "") or ""
        if len(content.strip()) < 10:
            return None

        # Take the most informative initial text of the statement (up to 7,500 chars)
        snippet = content[:7500]

        prompt = f"""Eres un experto en contabilidad y análisis financiero.
Analiza este fragmento de estado de cuenta o documento financiero y extrae EXCLUSIVAMENTE un objeto JSON válido con los datos clave.

Documento: {doc.get('title', '')}
Texto:
{snippet}

Responde ÚNICAMENTE con este esquema JSON (sin markdown ni texto extra):
{{
  "periodo": "YYYY-MM (mes del estado de cuenta, ej: 2026-05)",
  "saldo_inicial": 0.0,
  "depositos_pagos": 0.0,
  "compras_cargos": 0.0,
  "saldo_final": 0.0,
  "pago_minimo": 0.0,
  "pago_sin_intereses": 0.0,
  "resumen": "Resumen conciso en 1 o 2 oraciones del estado de cuenta",
  "gastos_principales": [
    {{"concepto": "Nombre comercio o cargo principal", "monto": 0.0}}
  ]
}}"""

        response = await self._call_gemini([{"role": "user", "content": prompt}], temperature=0.1)
        if not response:
            return None

        clean_json = response.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
            clean_json = re.sub(r"\n?```$", "", clean_json)

        try:
            parsed = json.loads(clean_json.strip())
        except Exception as e:
            logger.error(f"Failed to parse JSON for doc {document_id}: {e}\nResponse: {response}")
            return None

        # Determine year and month from period or document created date
        created_date = doc.get("created", "")[:10]  # YYYY-MM-DD
        period = parsed.get("periodo", "") or created_date[:7]
        try:
            parts = period.split("-")
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
        except Exception:
            year = int(created_date[:4]) if len(created_date) >= 4 else 0
            month = int(created_date[5:7]) if len(created_date) >= 7 else 0

        # Correspondent name
        corr_id = doc.get("correspondent")
        corr_name = ""
        if corr_id:
            all_corrs = await self.paperless.list_correspondents()
            for c in all_corrs:
                if c.get("id") == corr_id:
                    corr_name = c.get("name", "")
                    break

        record = {
            "document_id": document_id,
            "title": doc.get("title", ""),
            "correspondent": corr_name,
            "document_date": created_date,
            "year": year,
            "month": month,
            "period": period,
            "saldo_inicial": parsed.get("saldo_inicial", 0.0),
            "depositos_pagos": parsed.get("depositos_pagos", 0.0),
            "compras_cargos": parsed.get("compras_cargos", 0.0),
            "saldo_final": parsed.get("saldo_final", 0.0),
            "pago_minimo": parsed.get("pago_minimo", 0.0),
            "pago_sin_intereses": parsed.get("pago_sin_intereses", 0.0),
            "resumen": parsed.get("resumen", ""),
            "gastos_principales": parsed.get("gastos_principales", []),
        }

        self.db.save_financial(record)
        logger.info(f"Cached structured financials for doc {document_id} ({period})")
        return record

    async def sync_all_financial_documents(self) -> Dict[str, Any]:
        """Scans Paperless for statements and indexes any new ones into SQLite cache."""
        docs = await self.paperless.get_documents(query="Estado de Cuenta", page_size=100)
        # Also check correspondent BBVA or Plata
        docs_bbva = await self.paperless.get_documents(query="BBVA", page_size=100)
        seen_ids = set()
        unique_docs = []
        for d in docs + docs_bbva:
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                unique_docs.append(d)

        indexed = 0
        already_cached = 0
        for doc in unique_docs:
            if self.db.is_indexed(doc["id"]):
                already_cached += 1
            else:
                res = await self.extract_and_cache_financials(doc["id"])
                if res:
                    indexed += 1

        stats = self.db.get_stats()
        return {
            "total_scanned": len(unique_docs),
            "newly_indexed": indexed,
            "already_cached": already_cached,
            "database_stats": stats,
        }

    async def answer_user_query(self, user_query: str) -> Dict[str, Any]:
        """
        Routes and resolves user query with the lowest token footprint.
        """
        # Save user message
        self.db.save_message("user", user_query)

        query_lower = user_query.lower()

        # Detect year in query (e.g., 2024, 2025, 2026)
        year_match = re.search(r"\b(202[0-9])\b", query_lower)
        target_year = int(year_match.group(1)) if year_match else None

        # Detect bank / correspondent
        detected_bank = None
        if "bbva" in query_lower:
            detected_bank = "BBVA"
        elif "plata" in query_lower:
            detected_bank = "Plata"
        elif "santander" in query_lower:
            detected_bank = "Santander"
        elif "cfe" in query_lower:
            detected_bank = "CFE"

        # Check if financial / aggregate intent
        financial_keywords = [
            "cuanto gaste", "cuánto gasté", "gasto", "gastos", "total", "saldo", "saldos",
            "ingreso", "ingresos", "depositos", "depósitos", "historial", "estado de cuenta",
            "estados de cuenta", "anual", "año", "mes", "meses", "promedio", "resumen"
        ]
        is_financial = any(kw in query_lower for kw in financial_keywords)

        if is_financial:
            # Ensure documents are synced in SQLite
            await self.sync_all_financial_documents()

            # Determine target year if not specified: use latest year available in DB
            stats = self.db.get_stats()
            available_years = stats.get("years", [])
            if not target_year and available_years:
                target_year = available_years[-1]

            if target_year:
                # Retrieve local aggregate data (0 tokens)
                annual_data = self.db.get_annual_aggregation(year=target_year, correspondent=detected_bank)
                months = annual_data.get("meses", [])

                if months:
                    # Format compact summary table to feed Gemini
                    compact_table = []
                    for m in months:
                        compact_table.append({
                            "periodo": m.get("period"),
                            "banco": m.get("correspondent"),
                            "compras_cargos": m.get("compras_cargos"),
                            "depositos_pagos": m.get("depositos_pagos"),
                            "saldo_final": m.get("saldo_final"),
                            "pago_minimo": m.get("pago_minimo"),
                            "resumen": m.get("resumen")
                        })

                    system_prompt = """Eres DoChat, el asistente financiero personal del homelab de David.
Tienes a continuación los datos FINANCIEROS REALES extraídos de los estados de cuenta de Paperless calculados con total exactitud matemática.
Tu labor es responder a la pregunta del usuario de forma clara, profesional, amable y estructurada.
REGLAS ESTRICTAS DE FORMATO:
- NUNCA uses encabezados con almohadillas (#, ##, ###).
- Usa títulos destacados en **NEGRITA** y líneas divisorias (---).
- Usa viñetas limpias (•) y cantidades con formato de moneda mexicana ($1,234.56).
- No inventes cifras: básate 100% en los datos de la tabla."""

                    user_context = f"""Datos consolidados del año {target_year} (Banco: {detected_bank or 'Todos'}):
Total compras/gastos: ${annual_data.get('total_compras_cargos', 0):,.2f}
Total pagos/depósitos: ${annual_data.get('total_depositos_pagos', 0):,.2f}
Promedio mensual de gasto: ${annual_data.get('promedio_mensual_gasto', 0):,.2f}
Gasto mensual más alto: ${annual_data.get('max_gasto_mes', 0):,.2f}

Desglose mensual:
{json.dumps(compact_table, ensure_ascii=False, indent=2)}

Pregunta del usuario:
{user_query}"""

                    ai_reply = await self._call_gemini([
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_context}
                    ], temperature=0.3)

                    if ai_reply:
                        self.db.save_message("assistant", ai_reply)
                        return {
                            "response": ai_reply,
                            "type": "financial_summary",
                            "year": target_year,
                            "months_analyzed": len(months),
                            "tokens_saved": "Ahorro de ~95% usando agregación local SQLite"
                        }

        # Specific search query (e.g. search for specific merchant, keyword, bill)
        search_results = await self.paperless.search_full_text(user_query, max_results=3)
        if search_results:
            snippets = []
            for doc in search_results:
                content = doc.get("content", "") or ""
                # Extract relevant snippet around query words
                snippet = content[:1500] if len(content) > 1500 else content
                snippets.append({
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "fecha": doc.get("created", "")[:10],
                    "extracto": snippet
                })

            system_prompt = """Eres DoChat, el asistente documental del homelab de David.
A continuación se muestran los extractos de documentos encontrados en Paperless que coinciden con la búsqueda.
Responde de manera concisa y certera a la pregunta del usuario citando el nombre del documento y fecha."""

            ai_reply = await self._call_gemini([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Documentos encontrados:\n{json.dumps(snippets, ensure_ascii=False, indent=2)}\n\nPregunta: {user_query}"}
            ], temperature=0.2)

            if ai_reply:
                self.db.save_message("assistant", ai_reply)
                return {
                    "response": ai_reply,
                    "type": "search_result",
                    "sources": [s["title"] for s in snippets]
                }

        # Default conversational / helpful fallback
        system_prompt = """Eres DoChat, el asistente de documentos y estados de cuenta de Paperless de David.
Informa qué puedes hacer: analizar estados de cuenta por mes o año, comparar gastos, consultar saldos, o buscar transacciones específicas."""
        ai_reply = await self._call_gemini([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ], temperature=0.3)

        response_text = ai_reply or "Hola, puedo ayudarte a consultar y comparar tus estados de cuenta de BBVA u otros documentos en Paperless."
        self.db.save_message("assistant", response_text)
        return {
            "response": response_text,
            "type": "general"
        }
