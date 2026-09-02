"""Application construction and dependency assembly."""

from fastapi import FastAPI

from app.web.routes import router as mvp_router


def create_app() -> FastAPI:
    """Build an isolated AIHost application instance."""

    application = FastAPI(title="CUBIC AIHost Python MVP", version="0.1.0")
    application.include_router(mvp_router)
    return application
