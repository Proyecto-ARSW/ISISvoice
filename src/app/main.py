from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app.routers import triage_router, health_router, speech_router
from app.services.mongo_service import mongo_store

_CLIENT_HTML = Path(__file__).parent.parent.parent / "client.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    await mongo_store.connect()
    yield
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
    return RedirectResponse(url="/docs")


@app.get("/client.html", include_in_schema=False)
async def serve_client():
    """Serve the dev client at a fixed path — does not shadow API routes."""
    if _CLIENT_HTML.exists():
        return FileResponse(_CLIENT_HTML)
    return RedirectResponse(url="/docs")