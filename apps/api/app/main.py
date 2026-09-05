from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.health import router as health_router
from app.auth.router import limiter
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.documents.router import router as documents_router
from app.ingestion.router import router as ingestion_router
from app.knowledge.router import router as knowledge_router
from app.organizations.router import router as organizations_router
from app.parsing.router import router as parsing_router
from app.retrieval.router import router as retrieval_router


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Self-Service Regulatory Knowledge Assistant API",
        version="0.1.0",
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(organizations_router)
    app.include_router(knowledge_router)
    app.include_router(documents_router)
    app.include_router(parsing_router)
    app.include_router(ingestion_router)
    app.include_router(retrieval_router)

    return app


app = create_app()
