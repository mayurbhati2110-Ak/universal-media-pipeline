from fastapi import FastAPI

from app.api.media import router as media_router
from app.api.reasoning import router as reasoning_router

from app.core.config import settings


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Universal AI Media Processing Pipeline for "
        "video, audio, image, and PDF processing."
    ),
)


# Deterministic media processing APIs
app.include_router(media_router)

# Optional AI reasoning API
app.include_router(reasoning_router)


@app.get("/")
def root():
    return {
        "message": "Universal AI Media Processing Pipeline is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

