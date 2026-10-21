from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ticketrush:ticketrush@localhost:5432/ticketrush"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str  # required: no secret is hard-coded
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    hold_minutes: int = 5
    max_seats_per_booking: int = 6
    event_cache_ttl_seconds: int = 60
    login_rate_limit_per_min: int = 5
    booking_rate_limit_per_min: int = 10
    expiry_sweep_seconds: int = 30
    enable_sweeper: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
