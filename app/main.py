from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.controllers import chat_controller, ranking_controller
from app.controllers.university_controller import router as university_router
from app.controllers import book_controller
from app.controllers.demo_controller import router as demo_router
from app.controllers.ocr_preview_controller import router as ocr_preview_router
from app.core.mongo import mongo_db
import os

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="1.0.0",
    redirect_slashes=False,
)

# Internal API Key middleware — reject requests not coming from the BE
@app.middleware("http")
async def require_internal_api_key(request: Request, call_next):
    # Skip health/docs endpoints and static file serving
    if request.url.path in ("/", "/health", "/docs", "/openapi.json", "/redoc") \
            or request.url.path.startswith("/static/"):
        return await call_next(request)
    expected_key = settings.internal_api_key
    if expected_key:
        provided_key = request.headers.get("X-Internal-API-Key")
        if provided_key != expected_key:
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: missing or invalid API key"}
            )
    return await call_next(request)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for image storage
os.makedirs(settings.storage_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.storage_path), name="static")

API_PREFIX = getattr(settings, "api_prefix", "/api/v1")

# Include routers. Legacy chapter/lesson/content/search controllers were
# removed in the Phase 3 refactor — Postgres now owns the curriculum, and
# Mongo only serves OCR'd page content via book_controller.
app.include_router(chat_controller.router, prefix=API_PREFIX)
app.include_router(ranking_controller.router, prefix=API_PREFIX)
app.include_router(university_router, prefix=API_PREFIX)
app.include_router(book_controller.router, prefix=API_PREFIX)
app.include_router(book_controller.lesson_scoped_router, prefix=API_PREFIX)
app.include_router(demo_router, prefix=API_PREFIX)
app.include_router(ocr_preview_router, prefix=API_PREFIX)

# Health check endpoint
@app.get("/")
async def root():
    return {
        "message": "Chatbot Tư vấn Tuyển sinh API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            f"{API_PREFIX}/chat/",
            f"{API_PREFIX}/ranking/",
            "/docs"
        ]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "gemini": bool(settings.gemini_api_key),
        "gemini_model": settings.gemini_model,
        "mathpix": settings.mathpix_enabled,
    }


@app.on_event("startup")
async def create_indexes():
    if os.getenv("SKIP_DB_INIT"):
        return
    # `books` keyed by Postgres UUID — no extra index needed beyond _id.
    await mongo_db["books"].create_index("status")
    # The hot path: per-page lookup for the verify wizard. The compound
    # unique index doubles as a page-of-lesson read index since Mongo can
    # use a prefix.
    await mongo_db["lesson_pages"].create_index(
        [("book_id", 1), ("lesson_id", 1), ("page_number", 1)], unique=True
    )
    # Lesson-scoped lookup (Gemini prompt builder, book-agnostic).
    await mongo_db["lesson_pages"].create_index([("lesson_id", 1), ("book_id", 1)])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug
    )
