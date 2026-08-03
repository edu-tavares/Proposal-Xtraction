"""Configuração a partir de variáveis de ambiente (.env)."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# Cada provedor do LiteLLM espera a chave em uma env var própria. Mapeamos a partir
# do prefixo de LLM_MODEL para que o usuário só precise preencher LLM_API_KEY.
PROVIDER_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure": "AZURE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "vertex_ai": "VERTEXAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "fireworks_ai": "FIREWORKS_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""

    llm_model: str = "anthropic/claude-opus-5"
    llm_api_key: str = ""
    llm_api_base: str | None = None
    llm_max_output_tokens: int = 8000
    llm_temperature: float | None = 0.0
    llm_timeout_seconds: int = 180
    llm_num_retries: int = 2

    max_file_mb: int = 20
    max_pages: int = 15
    pdf_render_dpi: int = 150
    image_max_dimension: int = 2000

    log_level: str = "INFO"

    @property
    def provider(self) -> str:
        """Prefixo do provedor em LLM_MODEL (`anthropic/claude-opus-5` -> `anthropic`)."""
        return self.llm_model.split("/", 1)[0] if "/" in self.llm_model else ""

    def export_provider_key(self) -> str | None:
        """Publica LLM_API_KEY na env var que o provedor espera. Devolve o nome usado."""
        if not self.llm_api_key:
            return None
        env_name = PROVIDER_KEY_ENV.get(self.provider)
        if env_name is None:
            # Provedor desconhecido pelo mapa: LiteLLM ainda aceita a chave por parâmetro.
            return None
        os.environ.setdefault(env_name, self.llm_api_key)
        return env_name


_settings: Settings | None = None


def get_settings() -> Settings:
    """Instância única, carregada na primeira chamada."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Usado pelos testes para recarregar a configuração."""
    global _settings
    _settings = None
