from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from app.routes import health, api


class Settings(BaseSettings):
    SERVICE_ENV: str = "development"
    DATABASE_URL: str = (
        "postgresql://postgres:devpass123@localhost:5432/research_mind_db"
    )
    CORS_ORIGINS: str = "http://localhost:15000"

    class Config:
        env_file = ".env"


settings = Settings()

app = FastAPI(
    title="research-mind API",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(api.router, prefix="/api/v1")
