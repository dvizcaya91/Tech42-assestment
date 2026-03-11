from fastapi import FastAPI

from app.api.routes import router as api_router

try:
    from mangum import Mangum
except ImportError:  # pragma: no cover - optional until runtime dependencies are installed
    Mangum = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="AWS Agentcore Stock Assistant",
        version="0.1.0",
        description="FastAPI service for the assessment backend with a streaming query endpoint.",
    )
    app.include_router(api_router)
    return app


app = create_app()
handler = Mangum(app, lifespan="off") if Mangum is not None else None
