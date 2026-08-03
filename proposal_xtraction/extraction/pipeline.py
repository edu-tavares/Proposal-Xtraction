"""Orquestra loader + LLM + validação do schema."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError

from ..config import Settings, get_settings
from ..llm.base import ContentPart, LLMClient
from ..llm.prompts import SYSTEM_PROMPT, USER_INSTRUCTION
from ..models import Proposta, proposta_json_schema
from . import loader

log = structlog.get_logger(__name__)


@dataclass
class ExtractionResult:
    proposta: Proposta
    strategy: loader.Strategy
    pages: int
    truncated: bool
    model: str
    input_tokens: int | None
    output_tokens: int | None
    elapsed_seconds: float


def _validator(data: dict[str, Any]) -> list[str]:
    """Valida o JSON contra `Proposta` e devolve erros legíveis para o modelo."""
    # Todos os campos de `Proposta` são opcionais, então um objeto com a estrutura
    # errada validaria como proposta vazia. Rejeitamos antes que isso aconteça.
    if not set(Proposta.model_fields) & data.keys():
        return [
            "o objeto não contém nenhum campo do schema: os campos devem estar no "
            "nível raiz do JSON, não aninhados dentro de outra chave"
        ]
    try:
        Proposta.model_validate(data)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc']) or 'raiz'}: {err['msg']}"
            for err in exc.errors()[:10]
        ]
    return []


async def _ask(client: LLMClient, parts: list[ContentPart]):
    return await client.complete_json(
        system=SYSTEM_PROMPT,
        parts=[ContentPart.from_text(USER_INSTRUCTION), *parts],
        schema=proposta_json_schema(),
        schema_name="proposta",
        validator=_validator,
    )


async def extract(
    path: Path,
    client: LLMClient,
    settings: Settings | None = None,
) -> ExtractionResult:
    """Extrai a proposta do arquivo, com fallback de texto nativo para imagens."""
    settings = settings or get_settings()
    started = time.monotonic()

    document = loader.load(path, settings)
    result = await _ask(client, document.parts)
    proposta = Proposta.model_validate(result.data)

    # A camada de texto pode existir mas ser inútil (tabela em imagem dentro do PDF).
    if not proposta.itens and document.strategy == "texto_nativo":
        log.info("pipeline.fallback_para_imagens", motivo="nenhum item no texto nativo")
        document = loader.load_as_images(path, settings)
        retry = await _ask(client, document.parts)
        proposta = Proposta.model_validate(retry.data)
        result = retry

    return ExtractionResult(
        proposta=proposta,
        strategy=document.strategy,
        pages=document.pages,
        truncated=document.truncated,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        elapsed_seconds=round(time.monotonic() - started, 2),
    )
