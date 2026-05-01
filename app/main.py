from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.controllers import chat_controller, ranking_controller
from app.controllers.university_controller import router as university_router
from app.controllers import book_controller, chapter_controller, lesson_controller, search_controller
import os

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for image storage
os.makedirs(settings.storage_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.storage_path), name="static")

API_PREFIX = getattr(settings, "api_prefix", "/api/v1")

# Include routers
app.include_router(chat_controller.router, prefix=API_PREFIX)
app.include_router(ranking_controller.router, prefix=API_PREFIX)
app.include_router(university_router, prefix=API_PREFIX)
app.include_router(book_controller.router, prefix=API_PREFIX)
app.include_router(chapter_controller.router, prefix=API_PREFIX)
app.include_router(lesson_controller.router, prefix=API_PREFIX)
app.include_router(search_controller.router, prefix=API_PREFIX)

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
        "mathpix": settings.mathpix_enabled,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug
    )