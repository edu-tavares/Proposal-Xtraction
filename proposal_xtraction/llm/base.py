"""Contrato neutro de provedor. Nada aqui importa SDK de LLM."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

Validator = Callable[[dict[str, Any]], list[str]]
"""Recebe o JSON devolvido e retorna a lista de erros (vazia quando está válido)."""


class ContentPart(BaseModel):
    """Bloco de entrada independente de provedor: texto ou imagem."""

    kind: Literal["text", "image"]
    text: str | None = None
    image_b64: str | None = None
    media_type: str | None = None

    @classmethod
    def from_text(cls, text: str) -> ContentPart:
        return cls(kind="text", text=text)

    @classmethod
    def from_image_bytes(cls, data: bytes, media_type: str = "image/png") -> ContentPart:
        return cls(
            kind="image",
            image_b64=base64.b64encode(data).decode("ascii"),
            media_type=media_type,
        )

    def data_uri(self) -> str:
        return f"data:{self.media_type};base64,{self.image_b64}"


class LLMResult(BaseModel):
    """Resposta já parseada como JSON, com metadados de uso."""

    data: dict[str, Any]
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Interface que qualquer provedor precisa cumprir."""

    model: str

    async def complete_json(
        self,
        system: str,
        parts: list[ContentPart],
        schema: dict[str, Any],
        schema_name: str = "resposta",
        validator: Validator | None = None,
    ) -> LLMResult:
        """Envia `parts` ao modelo e devolve o JSON que satisfaz `schema`.

        Quando `validator` é informado e acusa erros, a implementação deve tentar
        uma correção com o modelo antes de desistir com `LLMBadOutput`.
        """
        ...


class LLMError(Exception):
    """Erro genérico da camada de LLM."""


class LLMRateLimited(LLMError):
    """O provedor recusou por limite de taxa/cota."""


class LLMInputTooLarge(LLMError):
    """O conteúdo enviado excede a janela de contexto do modelo."""


class LLMBadOutput(LLMError):
    """O modelo não devolveu JSON utilizável, mesmo após a retentativa."""


class LLMRefused(LLMError):
    """O modelo se recusou a processar o documento."""


class LLMModelNotFound(LLMError):
    """O modelo configurado não existe ou a chave não tem acesso a ele."""


class LLMAuthFailed(LLMError):
    """A chave do provedor é inválida ou não foi aceita."""
