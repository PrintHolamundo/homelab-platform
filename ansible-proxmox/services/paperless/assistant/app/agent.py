import asyncio
import json
import logging
from typing import Any
import httpx
from app.config import settings
from app.database import execute_read_only_query
from app.paperless import paperless
from app.sync import sync_financial_documents

logger = logging.getLogger("agent")

SYSTEM_INSTRUCTIONS = f"""Eres el Asistente Inteligente de Paperless-ngx para el homelab de David Haro.
Tienes acceso directo al archivo completo de documentos y a la base de datos financiera estructurada.

Tus capacidades mediante herramientas:
1. 'search_paperless': Busca cualquier documento en el archivo (pólizas de seguro, garantías, manuales, identificaciones, recibos, contratos, etc.) usando el motor de búsqueda de texto completo de Paperless.
2. 'read_document_details': Lee el texto OCR completo de un documento específico cuando necesites analizar cláusulas, fechas de vencimiento, detalles de póliza, etc.
3. 'query_expenses_sql': Ejecuta consultas SQL (SELECT) sobre la tabla estructurada 'transactions' para obtener totales exactos, sumas, promedios y desgloses de gastos SIN alucinaciones matemáticas.
   Esquema de 'transactions':
     - id: INTEGER
     - document_id: INTEGER (ID en Paperless)
     - date: TEXT (formato YYYY-MM-DD)
     - description: TEXT (nombre del comercio o concepto)
     - amount: REAL (monto del gasto o ingreso)
     - type: TEXT ('gasto' | 'ingreso' | 'transferencia')
     - category: TEXT ('Supermercado', 'Restaurantes', 'Servicios', 'Salud', 'Transporte', 'Tecnología', 'Nómina', 'General')
     - account_name: TEXT (banco o emisor)
4. 'sync_financial_documents': Sincroniza y procesa documentos financieros recientes de Paperless a la base de datos SQL.

Reglas fundamentales:
- Para preguntas sobre finanzas y gastos agregados ("¿Cuánto gasté en...?", "Top 5 gastos", "Total en junio"), usa SIEMPRE 'query_expenses_sql'. Las sumas deben ser exactas.
- Para preguntas sobre documentos específicos ("¿Qué cubre mi seguro de auto?", "¿Dónde está la factura de la laptop?", "¿Cuándo vence mi garantía?"), usa 'search_paperless' y lee el documento si requieres precisión.
- SIEMPRE proporciona enlaces en formato Markdown a los documentos relevantes usando el campo 'web_url' (ejemplo: [Factura de Luz](URL)).
- Si una consulta SQL no arroja resultados, sugiere al usuario sincronizar con 'sync_financial_documents' o busca directamente en los documentos vía 'search_paperless'.
- Responde siempre en español, de forma concisa, clara y estructurada.
"""

TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_paperless",
            "description": "Busca documentos en Paperless-ngx por texto libre, términos clave, etiquetas o personas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Término de búsqueda (ej. 'seguro auto', 'recibo CFE', 'garantia laptop')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Número máximo de resultados a retornar (por defecto 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document_details",
            "description": "Obtiene el texto OCR completo y metadatos de un documento específico por su ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "integer",
                        "description": "El ID numérico del documento en Paperless",
                    },
                },
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_expenses_sql",
            "description": "Ejecuta una consulta SQL SELECT sobre la base de datos de gastos y transacciones (tabla 'transactions') para cálculos exactos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {
                        "type": "string",
                        "description": "Consulta SQL SELECT válida para SQLite (ej. SELECT category, SUM(amount) FROM transactions WHERE strftime('%Y-%m', date) = '2024-05' GROUP BY category)",
                    },
                },
                "required": ["sql_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_financial_data",
            "description": "Inicia la sincronización incremental de documentos financieros recientes en Paperless hacia SQLite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Cantidad de documentos a revisar (por defecto 20)",
                    },
                },
            },
        },
    },
]

async def execute_tool(name: str, args: dict[str, Any]) -> Any:
    """Execute the requested tool and return the output payload."""
    try:
        if name == "search_paperless":
            query = args.get("query", "")
            limit = args.get("limit", 5)
            return await paperless.search_documents(query=query, page_size=limit)

        elif name == "read_document_details":
            doc_id = args.get("document_id")
            doc = await paperless.get_document_content(doc_id)
            # Truncate content to 8,000 characters to keep context clean and cheap
            if "content" in doc:
                doc["content"] = doc["content"][:8000]
            return doc

        elif name == "query_expenses_sql":
            sql = args.get("sql_query", "")
            results = execute_read_only_query(sql)
            return {"count": len(results), "rows": results}

        elif name == "sync_financial_data":
            # Cap sync during interactive chat to max 5 docs to prevent timeout
            limit = min(args.get("limit", 5), 5)
            res = await sync_financial_documents(limit=limit)
            return res

        else:
            return {"error": f"Tool '{name}' no reconocida."}
    except Exception as e:
        logger.error(f"Error executing tool {name} with args {args}: {e}")
        return {"error": str(e)}

async def run_chat_agent(
    user_message: str,
    conversation_history: list[dict[str, str]] = None,
) -> dict[str, Any]:
    """Agent loop: calls Gemini, runs tools if requested, and returns final answer."""
    if not settings.gemini_api_key:
        return {
            "response": "⚠️ La variable `GEMINI_API_KEY` no está configurada. Por favor configúrala en el entorno para habilitar las respuestas con IA.",
            "sources": [],
        }

    history = conversation_history or []
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]
    
    # Append recent chat history (limit to last 6 turns to conserve context)
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {settings.gemini_api_key}",
        "Content-Type": "application/json",
    }

    collected_sources: list[dict[str, Any]] = []
    max_rounds = 4

    # Generous timeout: 90s total, 10s connection
    timeout_config = httpx.Timeout(90.0, connect=10.0, read=90.0)

    try:
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            for round_idx in range(max_rounds):
                payload = {
                    "model": settings.ai_model,
                    "messages": messages,
                    "tools": TOOLS_DEFINITIONS,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                }

                # Retry up to 2 times on transient network / timeout errors
                res = None
                for attempt in range(2):
                    try:
                        res = await client.post(
                            f"{settings.ai_base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        if res.status_code == 200:
                            break
                        elif res.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                            logger.warning(f"LLM API returned {res.status_code}, retrying in 2s...")
                            await asyncio.sleep(2)
                            continue
                        else:
                            break
                    except (httpx.TimeoutException, httpx.NetworkError) as req_err:
                        if attempt == 0:
                            logger.warning(f"LLM request {type(req_err).__name__}, retrying in 2s...")
                            await asyncio.sleep(2)
                            continue
                        else:
                            logger.error(f"LLM request failed after retry: {req_err}")
                            return {
                                "response": "⏱️ El modelo de IA tardó demasiado en responder. Si hay una sincronización en curso o Paperless está ocupado, por favor espera un momento e intenta de nuevo.",
                                "sources": collected_sources,
                            }

                if res is None or res.status_code != 200:
                    status = res.status_code if res else "desconocido"
                    text = res.text[:200] if res else "Sin respuesta"
                    logger.error(f"LLM API Error ({status}): {text}")
                    return {
                        "response": f"⚠️ Error al comunicarse con el modelo de IA ({status}). Por favor intenta de nuevo.",
                        "sources": [],
                    }

                try:
                    data = res.json()
                    choice = data["choices"][0]
                    message_obj = choice["message"]
                    tool_calls = message_obj.get("tool_calls")
                except Exception as parse_err:
                    logger.error(f"Error parsing LLM response: {parse_err}, body: {res.text[:300]}")
                    return {
                        "response": "⚠️ Error interpretando la respuesta del modelo de IA. Intenta reformular tu pregunta.",
                        "sources": collected_sources,
                    }

                if not tool_calls:
                    # No more tools called, return final response
                    return {
                        "response": message_obj.get("content", ""),
                        "sources": collected_sources,
                    }

                # Append the assistant's tool call message
                messages.append(message_obj)

                # Execute tools
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"].get("arguments", "{}"))
                    except Exception:
                        fn_args = {}

                    tool_result = await execute_tool(fn_name, fn_args)

                    # Keep track of sources for the UI
                    if fn_name == "search_paperless" and isinstance(tool_result, dict):
                        for doc in tool_result.get("results", []):
                            if not any(s.get("id") == doc["id"] for s in collected_sources):
                                collected_sources.append({
                                    "id": doc["id"],
                                    "title": doc["title"],
                                    "url": doc["web_url"],
                                })
                    elif fn_name == "read_document_details" and isinstance(tool_result, dict):
                        if not any(s.get("id") == tool_result.get("id") for s in collected_sources):
                            collected_sources.append({
                                "id": tool_result.get("id"),
                                "title": tool_result.get("title"),
                                "url": tool_result.get("web_url"),
                            })

                    # Safely serialize tool result, limiting character length
                    content_str = json.dumps(tool_result, ensure_ascii=False)
                    if len(content_str) > 12000:
                        content_str = content_str[:12000] + "\n... [Resultado truncado por longitud]"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": content_str,
                    })

    except Exception as general_err:
        logger.error(f"General error in run_chat_agent: {general_err}", exc_info=True)
        return {
            "response": f"⚠️ Ocurrió una dificultad procesando la consulta: {str(general_err)}",
            "sources": collected_sources,
        }

    return {
        "response": "La consulta requirió demasiados pasos. Por favor sé más específico con los datos o fechas que buscas.",
        "sources": collected_sources,
    }
