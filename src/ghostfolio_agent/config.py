from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # LLM
    anthropic_api_key: str

    # Ghostfolio
    ghostfolio_base_url: str = "http://localhost:3333"
    ghostfolio_access_token: str

    # LangSmith
    langsmith_api_key: str = ""
    langchain_tracing_v2: bool = True
    langchain_project: str = "ghostfolio-agent"

    # App
    agent_port: int = 8000
    log_level: str = "debug"


def get_settings() -> Settings:
    return Settings()
