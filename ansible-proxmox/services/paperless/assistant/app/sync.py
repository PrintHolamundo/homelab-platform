import asyncio
import json
import logging
from typing import Any
import httpx
from app.config import settings
from app.database import (
    is_document_processed,
    record_document_and_transactions,
)
from app.paperless import paperless

logger = logging.getLogger("sync_service")

# Concurrency lock
_sync_lock = asyncio.Lock()
_sync_status = {
    "is_running": False,
    "last_run": None,
    "processed_count": 0,
    "skipped_count": 0,
    "errors": [],
}

EXTRACTION_SYSTEM_PROMPT = """Eres un experto contable y auditor financiero.
Analiza el siguiente texto OCR extraído de un estado de cuenta bancario, factura, recibo o nómina.
Extrae todas las transacciones o cargos individuales detectados en formato JSON estricto.

Reglas:
1. Devuelve ÚNICAMENTE un array JSON válido de objetos con este formato:
[
  {
    "date": "YYYY-MM-DD",
    "description": "Nombre del comercio o concepto",
    "amount": 123.45,
    "type": "gasto" | "ingreso" | "transferencia",
    "category": "Supermercado" | "Restaurantes" | "Servicios" | "Salud" | "Transporte" | "Tecnología" | "Nómina" | "Impuestos" | "Finanzas" | "General"
  }
]
2. El monto ('amount') siempre debe ser un número positivo (float/int).
3. Si la fecha solo indica día/mes, asume el año indicado en el documento.
4. Si el documento es un recibo con una sola compra/total, genera un único elemento con el total.
5. Si el documento no contiene transacciones financieras válidas, responde con una lista vacía: []
"""

async def extract_transactions_with_llm(doc_title: str, doc_content: str) -> list[dict[str, Any]]:
    """Extract structured transactions from OCR text using Gemini OpenAI-compatible endpoint."""
    if not settings.gemini_api_key:
        logger.warning("No GEMINI_API_KEY configured; skipping AI extraction.")
        return []

    # Limit text to 15,000 characters to prevent excessive token usage while covering 99% of statements
    snippet = doc_content[:15000]

    headers = {
        "Authorization": f"Bearer {settings.gemini_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.ai_model,
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Documento: {doc_title}\n\nTexto OCR:\n{snippet}\n\nExtrae las transacciones en JSON:",
            },
        ],
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{settings.ai_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
            raw_text = data["choices"][0]["message"]["content"].strip()

            # Clean markdown codeblocks if returned
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            transactions = json.loads(raw_text)
            if isinstance(transactions, list):
                return transactions
            return []
    except Exception as e:
        logger.error(f"Error extracting transactions for {doc_title}: {e}")
        return []

async def sync_financial_documents(limit: int = 50) -> dict[str, Any]:
    """Scan recent documents matching financial criteria and populate SQLite."""
    global _sync_status

    if _sync_lock.locked():
        return {"status": "already_running", "message": "Sync is already in progress."}

    async with _sync_lock:
        _sync_status["is_running"] = True
        _sync_status["processed_count"] = 0
        _sync_status["skipped_count"] = 0
        _sync_status["errors"] = []

        try:
            # Query Paperless for documents matching common financial search terms
            search_query = " OR ".join(settings.financial_tags)
            search_res = await paperless.search_documents(query=search_query, page_size=limit)
            documents = search_res.get("results", [])

            for doc_summary in documents:
                doc_id = doc_summary["id"]
                modified = doc_summary.get("modified", "")

                # Incremental check: Avoid re-processing if already indexed with same modification date
                if is_document_processed(doc_id, modified):
                    _sync_status["skipped_count"] += 1
                    continue

                try:
                    # Fetch full OCR content
                    full_doc = await paperless.get_document_content(doc_id)
                    content = full_doc.get("content", "")

                    if not content or len(content.strip()) < 20:
                        _sync_status["skipped_count"] += 1
                        continue

                    # Extract transactions via LLM
                    transactions = await extract_transactions_with_llm(
                        doc_title=full_doc.get("title", ""),
                        doc_content=content,
                    )

                    record_document_and_transactions(
                        document_id=doc_id,
                        title=full_doc.get("title", f"Doc #{doc_id}"),
                        created_date=full_doc.get("created", "")[:10],
                        modified_date=modified,
                        doc_type=full_doc.get("document_type") or "Financiero",
                        correspondent=full_doc.get("correspondent") or "",
                        transactions=transactions,
                    )
                    _sync_status["processed_count"] += 1

                except Exception as doc_err:
                    err_msg = f"Doc {doc_id}: {str(doc_err)}"
                    logger.error(err_msg)
                    _sync_status["errors"].append(err_msg)

        finally:
            _sync_status["is_running"] = False
            from datetime import datetime, timezone
            _sync_status["last_run"] = datetime.now(timezone.utc).isoformat()

        return dict(_sync_status)

def get_sync_status() -> dict[str, Any]:
    return dict(_sync_status)
