"""
api.py — FastAPI application with validated PDF serving.
All version strings env-driven.
"""

import os
import logging
import hashlib
import warnings
import multiprocessing.resource_tracker

# Suppress harmless 'leaked semaphore' warnings from uvicorn reloader shutdown
warnings.filterwarnings("ignore", message=".*resource_tracker.*leaked.*",
                        category=UserWarning)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from orchestrator import Orchestrator

from core.config import normalize_context
from core.pdf_downloader import PDFDownloader
from schemas import (
    DiscoverRequest, SummarizeRequest, AnalyzeRequest,
    CompareRequest, ImplementRequest,
    DiscoverResponse, AnalyzeResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

APP_NAME = os.getenv("APP_NAME", "CogniView.AI API")
APP_VERSION = os.getenv("APP_VERSION", "9.0.0")
SERVICE_NAME = os.getenv("SERVICE_NAME", "CogniView.AI")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()
pdf_downloader = PDFDownloader()
PDF_DIR = os.getenv("PDF_DOWNLOAD_DIR", "./downloaded_pdfs")
API_BASE_URL = f"http://localhost:{API_PORT}"


@app.get("/")
async def root():
    return {"service": SERVICE_NAME, "status": "running", "version": APP_VERSION}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/discover", response_model=DiscoverResponse)
async def discover_papers(request: DiscoverRequest):
    ctx = normalize_context(request)
    try:
        result = await orchestrator.discover_papers(ctx)
        return DiscoverResponse(**result)
    except Exception as e:
        logger.error(f"[API] Discover error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize", response_model=AnalyzeResponse)
async def summarize_paper(request: SummarizeRequest):
    ctx = normalize_context(request)
    ctx["topic"] = (request.topic or "").strip()
    paper_dict = {}
    if request.paper:
        paper_dict = request.paper.model_dump() if hasattr(request.paper, "model_dump") else request.paper.dict()
    try:
        result = await orchestrator.summarize_single_paper(ctx, paper_dict)
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"[API] Summarize error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    ctx = normalize_context(request)
    ctx["topic"] = (request.topic or "").strip()
    try:
        result = await orchestrator.run_pipeline(ctx)
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"[API] Analyze error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/implement", response_model=AnalyzeResponse)
async def implement_topic(request: ImplementRequest):
    ctx = normalize_context(request)
    ctx["topic"] = (request.topic or "").strip()
    ctx["mode"] = "implement"
    papers_list = []
    if request.papers:
        papers_list = [p if isinstance(p, dict) else (p.model_dump() if hasattr(p, "model_dump") else p.dict()) for p in request.papers]
    try:
        result = await orchestrator.implement_with_papers(ctx, papers_list)
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"[API] Implement error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compare", response_model=AnalyzeResponse)
async def compare_papers_endpoint(request: CompareRequest):
    ctx = normalize_context(request)
    ctx["topic"] = (request.topic or "").strip()
    ctx["mode"] = "compare"
    papers_list = []
    if request.papers:
        papers_list = [p if isinstance(p, dict) else (p.model_dump() if hasattr(p, "model_dump") else p.dict()) for p in request.papers]
    try:
        result = await orchestrator.compare_selected_papers(ctx, papers_list)
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"[API] Compare error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF and return paper-like metadata for direct pipeline use."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    os.makedirs(PDF_DIR, exist_ok=True)
    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="File appears to be empty or too small.")

    pdf_hash = hashlib.md5(content).hexdigest()
    filepath = os.path.join(PDF_DIR, f"{pdf_hash}.pdf")
    with open(filepath, "wb") as f:
        f.write(content)

    # Derive a readable title from the filename
    title = os.path.splitext(file.filename)[0].replace("_", " ").replace("-", " ").strip()

    logger.info(f"[API] Uploaded PDF: {file.filename} -> {pdf_hash}")
    return {
        "title": title,
        "pdf_hash": pdf_hash,
        "pdf_url": f"{API_BASE_URL}/pdf/{pdf_hash}",
        "filename": file.filename,
        "size": len(content),
    }



@app.get("/pdf/{pdf_hash}")
async def serve_pdf(pdf_hash: str, page: int = 1):
    filepath = os.path.join(PDF_DIR, f"{pdf_hash}.pdf")
    if not pdf_downloader.validate_existing(filepath):
        raise HTTPException(status_code=404, detail="PDF not found or invalid")
    return FileResponse(filepath, media_type="application/pdf",
                        headers={"Content-Disposition": "inline", "X-Page": str(page)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=True)
    