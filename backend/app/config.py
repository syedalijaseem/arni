from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Arni"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # MongoDB
    MONGODB_URL: str = "mongodb://mongodb:27017"
    MONGODB_DB_NAME: str = "arni"

    # Redis
    REDIS_URL: str = "redis://redis:6379"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    FRONTEND_URL: str = "http://localhost:5173"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""

    # Daily.co
    DAILY_API_KEY: str = ""
    DAILY_API_URL: str = "https://api.daily.co/v1"
    
    # Deepgram
    DEEPGRAM_API_KEY: str = ""

    # Wake Word Detection
    WAKE_PHRASES: str = (
        "hey arni,hey arnie,hey ardy,hey ardie,hey r.d.,hey rd,hey r d,"
        "hey ani,hey ernie,hey arnee,hey are knee,"
        "arni,arnie,ardy,ardie,r.d.,rd,r d,ani,ernie,arnee,are knee,"
        "harney,marni"
    )
    WAKE_COOLDOWN_SECONDS: int = 5
    CONVERSATION_WINDOW_SECONDS: int = 30
    UTTERANCE_SILENCE_MS: int = 800
    QUEUE_MAX_AGE_MS: int = 3000

    # AI / Claude
    ANTHROPIC_API_KEY: str = ""
    AI_CONTEXT_WINDOW: int = 20
    AI_MAX_RESPONSES: int = 30

    # OpenAI (Embeddings)
    OPENAI_API_KEY: str = ""

    # Document Upload
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_DOCS_PER_MEETING: int = 10

    # ElevenLabs (TTS)
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"
    ELEVENLABS_MODEL: str = "eleven_flash_v2_5"

    # Fact Check
    FACT_CHECK_CONFIDENCE_THRESHOLD: float = 0.85
    FACT_CHECK_COOLDOWN_SECONDS: int = 30

    # Meetings
    HOST_GRACE_PERIOD_MINUTES: int = 10

    # Rolling Summary Scheduler
    AUTO_SUMMARY_INTERVAL_MINUTES: int = 10

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
