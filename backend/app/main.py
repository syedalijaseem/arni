from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import connect_to_mongo, close_mongo_connection, get_database
from app.routers.auth import router as auth_router
from app.routers.meetings import router as meetings_router
from app.routers.transcripts import router as transcripts_router
from app.routers.ai import router as ai_router
import daily

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    daily.Daily.init()
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(meetings_router, prefix="/meetings", tags=["meetings"])
app.include_router(transcripts_router, prefix="/transcripts", tags=["transcripts"])
app.include_router(ai_router, prefix="/ai", tags=["ai"])


@app.get("/health")
async def health_check():
    """Health check endpoint — verifies API and MongoDB are running."""
    db = get_database()
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
    }
