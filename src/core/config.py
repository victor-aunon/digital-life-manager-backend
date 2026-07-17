from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="PostgreSQL Connection URL")
    ENCRYPTION_KEY: str = Field(..., description="Base64 encoded AES-256 Fernet Key")
    STAGING_DIR: str = Field(..., description="Absolute path to staging directory")
    O2_SYNC_DIR: str = Field(..., description="Absolute path to O2 Cloud synchronization directory")
    
    R2_ACCESS_KEY_ID: str = Field(..., description="Cloudflare R2 Access Key ID")
    R2_SECRET_ACCESS_KEY: str = Field(..., description="Cloudflare R2 Secret Access Key")
    R2_ENDPOINT_URL: str = Field(..., description="Cloudflare R2 Endpoint URL")
    R2_BUCKET_NAME: str = Field(..., description="Cloudflare R2 Bucket Name")
    
    LOCAL_LLM_URL: str = Field("http://localhost:11434/api/embeddings", description="Ollama API endpoint for embeddings")
    SIGNAL_ATTACHMENTS_DIR: str = Field(..., description="Absolute path to signal-cli attachments directory")
    MAX_HOT_SIZE_MB: int = Field(50, description="Maximum size in MB for a file to be routed to hot storage (R2)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
