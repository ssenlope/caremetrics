from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://caremetrics:caremetrics@localhost:5432/caremetrics"


settings = Settings()
