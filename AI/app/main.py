# AutomationCvEmail/app/main.py
import os
from fastapi import FastAPI
from app.core.config import settings
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes import router as api_v1_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("app/static/generated", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(api_v1_router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Edukai CV Automation"}

