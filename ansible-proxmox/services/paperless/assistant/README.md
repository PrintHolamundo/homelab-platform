# Paperless AI Assistant 📑🤖

Microservicio modular y ligero para consultar en lenguaje natural cualquier documento archivado en Paperless-ngx (pólizas, garantías, contratos, cartas, manuales) y ejecutar analíticas exactas sobre recibos y estados de cuenta bancarios.

## Características

- **RAG Agentic & Búsqueda Híbrida:** Utiliza el motor de búsqueda por texto completo (FTS) nativo de Paperless-ngx para recuperación local a costo cero, enviando únicamente fragmentos relevantes a Gemini Flash para no saturar tokens ni recursos.
- **Cálculo Financiero Determinista (Zero Alucinaciones):** Extrae y estructura las transacciones financieras en una base de datos SQLite local (`assistant.db`). Las consultas agregadas (*"¿Cuánto gasté en restaurantes en mayo?"*, *"Top 5 gastos del mes"*) se responden mediante consultas SQL (`SELECT`) ejecutadas directamente, garantizando 100% de precisión matemática.
- **Detección Anti-Duplicados:** Registro de sincronización incremental por `document_id` y `modified_date`. Solo procesa documentos nuevos o que hayan sido editados en Paperless.
- **Mini Web UI Moderna:** Interfaz web lista para usar (Tailwind CSS, Lucide Icons, Markdown con tablas y enlaces directos a los PDFs en Paperless).
- **Seguridad en Red Interna:** Se comunica directamente con Paperless dentro de la red privada Docker `paperless_net` vía `http://paperless:8000/api`.

## Estructura de Archivos

```
ansible-proxmox/services/paperless/assistant/
├── Dockerfile              # Imagen Python 3.12 slim optimizada
├── requirements.txt        # FastAPI, Uvicorn, HTTPX, Pydantic
├── README.md               # Documentación del servicio
├── app/
│   ├── __init__.py
│   ├── config.py           # Variables de entorno y configuración
│   ├── paperless.py        # Cliente HTTP asíncrono para la API de Paperless
│   ├── database.py         # SQLite local, esquema de transacciones y SQL seguro
│   ├── sync.py             # Sincronización incremental y extracción estructurada
│   ├── agent.py            # Orquestador del agente con Function Calling
│   └── main.py             # API REST FastAPI y endpoints
└── static/
    └── index.html          # Interfaz web de chat responsiva
```

## Endpoints API

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `GET` | `/` | Interfaz web de chat responsiva |
| `POST` | `/api/chat` | Endpoint de conversación con el agente |
| `POST` | `/api/sync` | Inicia sincronización en segundo plano de documentos financieros |
| `GET` | `/api/sync/status` | Estado actual del proceso de sincronización |
| `GET` | `/api/stats` | Estadísticas de documentos indexados y transacciones |
| `GET` | `/api/health` | Verificación de salud del microservicio |

## Variables de Entorno

- `PAPERLESS_API_URL`: URL interna de la API de Paperless (`http://paperless:8000/api`)
- `PAPERLESS_API_TOKEN`: Token de autenticación de Paperless
- `BASE_PAPERLESS_URL`: URL externa para generar enlaces clicables a los PDFs (`https://paperless.davidharo.store`)
- `GEMINI_API_KEY`: Clave de API de Google AI Studio / Gemini
- `AI_MODEL`: Modelo utilizado (por defecto `gemini-2.5-flash`)
- `DATA_DIR`: Directorio persistente para la base de datos SQLite (`/app/data`)
