"""Escolhe e monta o cliente de LLM a partir da configuração."""

from __future__ import annotations

import structlog

from ..config import Settings, get_settings
from .base import LLMClient
from .litellm_client import LiteLLMClient

log = structlog.get_logger(__name__)


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Constrói o cliente configurado em `LLM_MODEL`.

    Hoje só existe a implementação LiteLLM, que já cobre dezenas de provedores.
    Um adapter nativo por SDK entraria aqui sem afetar o resto do código.
    """
    settings = settings or get_settings()
    env_name = settings.export_provider_key()

    client = LiteLLMClient(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        api_base=settings.llm_api_base,
        max_output_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        num_retries=settings.llm_num_retries,
    )

    if not client.supports_vision():
        log.warning(
            "llm.sem_suporte_a_visao",
            model=settings.llm_model,
            detalhe="propostas escaneadas ou em foto podem falhar com este modelo",
        )

    log.info(
        "llm.configurado",
        model=settings.llm_model,
        provider=settings.provider or "desconhecido",
        api_base=settings.llm_api_base or "padrão do provedor",
        chave_via=env_name or "parâmetro da chamada",
    )
    return client
