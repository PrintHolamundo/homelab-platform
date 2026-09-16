import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from db import Database
from paperless_client import PaperlessClient
from analyzer import DocumentAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("dochat")

# Environment variables
PAPERLESS_URL = os.getenv("PAPERLESS_URL", "http://paperless:8000")
PAPERLESS_TOKEN = os.getenv("PAPERLESS_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/dochat.db")

db = Database(DATABASE_PATH)
paperless = PaperlessClient(PAPERLESS_URL, PAPERLESS_TOKEN)
analyzer = DocumentAnalyzer(
    paperless=paperless,
    db=db,
    gemini_api_key=GEMINI_API_KEY,
    gemini_base_url=GEMINI_BASE_URL,
    gemini_model=GEMINI_MODEL,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DoChat service...")
    try:
        # Check connection to Paperless
        corrs = await paperless.list_correspondents()
        logger.info(f"Connected to Paperless successfully ({len(corrs)} correspondents found)")
    except Exception as e:
        logger.warning(f"Could not connect to Paperless on startup: {e}")
    yield
    logger.info("Shutting down DoChat service...")


app = FastAPI(title="DoChat", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class ChatRequest(BaseModel):
    query: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = db.get_stats()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"stats": stats},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dochat"}


@app.get("/api/stats")
async def get_stats():
    return db.get_stats()


@app.get("/api/history")
async def get_history(limit: int = 20):
    return db.get_recent_history(limit)


@app.post("/api/sync")
async def sync_documents():
    try:
        res = await analyzer.sync_all_financial_documents()
        return res
    except Exception as e:
        logger.error(f"Sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        res = await analyzer.answer_user_query(req.query.strip())
        return res
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
