from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from pathlib import Path
import logging

from app.routers import triage_router, health_router, speech_router
from app.services.mongo_service import mongo_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    try:
        await mongo_store.connect()
    except Exception as exc:
        # Keep API available even if MongoDB is temporarily unreachable.
        logger.warning("MongoDB unavailable at startup, running in degraded mode: %s", exc)
    yield
    # Shutdown
    await mongo_store.close()


app = FastAPI(
    title="Voice Medical Triage Service",
    description="Microservice for clinical triage data extraction from voice and text",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(triage_router.router)
app.include_router(health_router.router)
app.include_router(speech_router.router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root to client.html or docs."""
    return RedirectResponse(url="/docs")


# Serve static files (client.html if exists)
static_dir = Path(__file__).parent.parent.parent
if (static_dir / "client.html").exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
