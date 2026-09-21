from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.extractions import router as extractions_router
from app.api.reviews import router as reviews_router
from app.api.results import router as results_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")
app.include_router(documents_router)
app.include_router(extractions_router)
app.include_router(reviews_router)
app.include_router(results_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}
