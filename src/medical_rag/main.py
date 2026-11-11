import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI

from medical_rag import __version__
from medical_rag.api.routes import router
from medical_rag.config import Settings
from medical_rag.llm.ollama_client import OllamaClient
from medical_rag.rag.chunker import load_chunks
from medical_rag.rag.retriever import Bm25Retriever, Retriever

logger = logging.getLogger("medical_rag")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(
    settings: Settings | None = None,
    retriever: Retriever | None = None,
    ollama: OllamaClient | None = None,
) -> FastAPI:
    settings = settings or Settings()
    # İstemci yaşam döngüsünden önce de hazır olsun. Aksi halde ilk istek
    # lifespan çalışmadan gelirse ollama None kalır.
    http: httpx.AsyncClient | None = None
    if ollama is None:
        http = httpx.AsyncClient()
        ollama = OllamaClient(settings, http)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        try:
            yield
        finally:
            client = app.state.http
            if client is not None:
                await client.aclose()

    app = FastAPI(title="Medical RAG", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.http = http
    app.state.ollama = ollama
    if retriever is None:
        chunks = load_chunks(settings.corpus_dir, settings.chunk_size, settings.chunk_overlap)
        retriever = Bm25Retriever(chunks, settings.bm25_score_threshold)
    app.state.retriever = retriever
    app.include_router(router)
    logger.info("app_ready model=%s num_ctx=%s", settings.model, settings.num_ctx)
    return app


app = create_app()


def run() -> None:
    configure_logging()
    # API de loopback'te kalır. Ağ arayüzüne açılmaz.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
