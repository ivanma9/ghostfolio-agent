from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from ghostfolio_agent.config import get_settings
from ghostfolio_agent.api.chat import router as chat_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("starting ghostfolio-agent", port=settings.agent_port)
    yield
    logger.info("shutting down ghostfolio-agent")


app = FastAPI(
    title="Ghostfolio Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
