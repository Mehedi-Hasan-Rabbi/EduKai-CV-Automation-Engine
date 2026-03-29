# AutomationCvEmail/app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Edukai Automation"
    OPENAI_API_KEY: str
    REDIS_URL: str = "redis://redis:6379/3"
    APP_BASE_URL: str = "http://127.0.0.1:8000/"
    
    class Config:
        env_file = ".env"
        extra = "ignore" 

settings = Settings()