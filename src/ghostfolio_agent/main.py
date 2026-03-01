import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import structlog

from ghostfolio_agent.config import get_settings
from ghostfolio_agent.logging_config import configure_logging
from ghostfolio_agent.api.chat import router as chat_router
from ghostfolio_agent.api.middleware import RequestLoggingMiddleware

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "static"


settings = get_settings()
configure_logging(log_level=settings.log_level, log_format=settings.log_format)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting ghostfolio-agent", port=settings.agent_port)
    yield
    logger.info("shutting down ghostfolio-agent")


app = FastAPI(
    title="Ghostfolio Agent",
    version="0.1.0",
    lifespan=lifespan,
)
_allowed_origins = (
    [settings.domain] if settings.domain else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(chat_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files (built React app) — must come after API routes
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
