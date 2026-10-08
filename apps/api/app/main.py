import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.analysis import router as analysis_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router

app = FastAPI(
    title="Archaeologist API",
    description="Static codebase analysis API for local development.",
    version="0.1.0",
)

configured_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in configured_origins.split(",")
    if origin.strip()
]
if not allowed_origins:
    allowed_origins = ["http://localhost:3000", "http://localhost:3001"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health_router, prefix="/api")
# Keep the original health URL available for existing local clients.
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(analysis_router)
