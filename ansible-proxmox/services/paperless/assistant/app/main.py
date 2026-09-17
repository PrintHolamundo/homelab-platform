import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import run_chat_agent
from app.config import settings
from app.database import init_db, get_stats
from app.paperless import paperless
from app.sync import sync_financial_documents, get_sync_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("assistant_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Paperless Assistant...")
    init_db()
    # Cache metadata from Paperless in background
    asyncio.create_task(paperless.get_metadata_mappings())
    yield
    # Shutdown
    logger.info("Shutting down Paperless Assistant...")

app = FastAPI(
    title="Paperless AI Assistant",
    description="Intelligent natural language & analytics assistant for Paperless-ngx",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[list[ChatMessage]] = []

class SyncRequest(BaseModel):
    limit: Optional[int] = 30

# API Endpoints
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "paperless-assistant",
        "version": "1.0.0",
    }

@app.get("/api/stats")
async def read_stats():
    try:
        db_stats = get_stats()
        return {"status": "ok", "data": db_stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío.")

    history_dicts = [{"role": m.role, "content": m.content} for m in req.history or []]
    
    result = await run_chat_agent(
        user_message=req.message,
        conversation_history=history_dicts,
    )
    return result

@app.post("/api/sync")
async def trigger_sync(req: SyncRequest, background_tasks: BackgroundTasks):
    current = get_sync_status()
    if current.get("is_running"):
        return {"status": "in_progress", "message": "La sincronización ya está en curso."}

    background_tasks.add_task(sync_financial_documents, limit=req.limit or 30)
    return {"status": "started", "message": "Sincronización iniciada en segundo plano."}

@app.get("/api/sync/status")
async def sync_status():
    return get_sync_status()

# Static Files & Web UI
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(
        "/app/static/index.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
