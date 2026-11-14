from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables / .env."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Hire My Chef API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://hmc_user:hmc_pass@localhost:5432/hire_my_chef"
    secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173"
    access_token_expire_minutes: int = 60
    reset_token_expire_minutes: int = 30
    jwt_algorithm: str = "HS256"
    ai_index_path: str = "data/chef_index.joblib"
    ai_review_snippets: int = 5  # recent review comments added to each chef document

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
