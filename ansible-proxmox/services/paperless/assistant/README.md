# Paperless AI Assistant

Lightweight microservice providing natural language document search and deterministic financial transaction analytics for Paperless-ngx documents using Google Gemini.

## Running the Service

The assistant runs as part of the Paperless Docker Compose stack:

```bash
docker compose up -d paperless-assistant
```

Access the chat web interface at `http://<host>:8050/`.

## Environment Variables

- `PAPERLESS_API_URL`: Internal Paperless API endpoint (`http://paperless:8000/api`).
- `PAPERLESS_API_TOKEN`: Authentication token for Paperless.
- `BASE_PAPERLESS_URL`: Public base URL for Paperless document links.
- `GEMINI_API_KEY`: Google Gemini API key.
- `AI_MODEL`: LLM model identifier (default: `gemini-3.5-flash-lite`).
- `DATA_DIR`: Persistent storage directory for SQLite database (default: `/app/data`).
