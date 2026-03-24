from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from pathlib import Path
from app.routers import speech_router
from app.services.mongo_service import mongo_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await mongo_store.close()

app = FastAPI(
    title="Voice Service API",
    description="API para transcripción de voz en tiempo real",
    version="2.1.0",
    lifespan=lifespan,
)

# Configurar CORS para permitir solicitudes desde diferentes orígenes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir router de speech
app.include_router(speech_router.router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/client.html")

# Servir archivos estáticos (HTML, CSS, JS)
# Buscar en el directorio padre del proyecto
static_dir = Path(__file__).parent.parent.parent
if (static_dir / "client.html").exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
