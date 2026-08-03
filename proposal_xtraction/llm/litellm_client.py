"""Implementação padrão de `LLMClient` sobre LiteLLM (multi-provedor)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import structlog

from .base import (
    ContentPart,
    LLMAuthFailed,
    LLMBadOutput,
    LLMError,
    LLMInputTooLarge,
    LLMModelNotFound,
    LLMRateLimited,
    LLMRefused,
    LLMResult,
)
from .prompts import REPAIR_INSTRUCTION

log = structlog.get_logger(__name__)

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

Validator = Callable[[dict[str, Any]], list[str]]


def parse_json_loose(text: str) -> dict[str, Any]:
    """Parseia o JSON da resposta tolerando cercas de código e texto ao redor."""
    if not text or not text.strip():
        raise ValueError("resposta vazia")

    candidate = text.strip()
    fenced = _FENCE_RE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # Último recurso: recorta do primeiro '{' até o último '}'.
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("nenhum objeto JSON encontrado na resposta") from None
        parsed = json.loads(candidate[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError(f"esperado objeto JSON, veio {type(parsed).__name__}")
    return parsed


class LiteLLMClient:
    """Fala com qualquer provedor suportado pela LiteLLM usando um formato único."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        max_output_tokens: int = 8000,
        temperature: float | None = 0.0,
        timeout: int = 180,
        num_retries: int = 2,
    ) -> None:
        self.model = model
        self.api_key = api_key or None
        self.api_base = api_base or None
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.num_retries = num_retries

    # -- capacidades do provedor -------------------------------------------------

    def _supports_response_schema(self) -> bool:
        import litellm

        try:
            return bool(litellm.supports_response_schema(model=self.model))
        except Exception:
            return False

    def supports_vision(self) -> bool:
        import litellm

        try:
            return bool(litellm.supports_vision(model=self.model))
        except Exception:
            # Modelo desconhecido pelo catálogo (ex.: proxy local): assumimos que sim
            # e deixamos o erro aparecer na chamada, se houver.
            return True

    def _response_format(self, schema: dict[str, Any], schema_name: str) -> dict[str, Any] | None:
        if self._supports_response_schema():
            return {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }
        return {"type": "json_object"}

    # -- construção das mensagens ------------------------------------------------

    @staticmethod
    def _to_message_content(parts: list[ContentPart]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for part in parts:
            if part.kind == "text":
                content.append({"type": "text", "text": part.text or ""})
            else:
                content.append({"type": "image_url", "image_url": {"url": part.data_uri()}})
        return content

    # -- chamada -----------------------------------------------------------------

    async def complete_json(
        self,
        system: str,
        parts: list[ContentPart],
        schema: dict[str, Any],
        schema_name: str = "resposta",
        validator: Validator | None = None,
    ) -> LLMResult:
        """Uma chamada ao modelo e, se o JSON não passar, uma única retentativa de correção."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": self._to_message_content(parts)},
        ]
        response_format = self._response_format(schema, schema_name)

        if not self._supports_response_schema():
            # Sem saída estruturada nativa: o schema vai no prompt.
            messages[0]["content"] += "\n\nSchema JSON esperado:\n" + json.dumps(
                schema, ensure_ascii=False
            )

        totals = {"input": 0, "output": 0}
        errors: list[str] = []

        for attempt in (1, 2):
            text, usage = await self._call(messages, response_format)
            totals["input"] += usage[0] or 0
            totals["output"] += usage[1] or 0

            try:
                data = parse_json_loose(text)
                errors = validator(data) if validator else []
                if not errors:
                    return LLMResult(
                        data=data,
                        model=self.model,
                        input_tokens=totals["input"] or None,
                        output_tokens=totals["output"] or None,
                    )
            except ValueError as exc:
                errors = [str(exc)]

            if attempt == 2:
                break

            log.warning("llm.json_invalido", model=self.model, erros=errors[:5])
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": REPAIR_INSTRUCTION.format(
                        errors="\n".join(f"- {e}" for e in errors)
                    ),
                }
            )

        raise LLMBadOutput(
            "o modelo não devolveu um JSON válido após a correção: " + "; ".join(errors[:5])
        )

    async def _call(
        self, messages: list[dict[str, Any]], response_format: dict[str, Any] | None
    ) -> tuple[str, tuple[int | None, int | None]]:
        import litellm

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_output_tokens,
            "timeout": self.timeout,
            "num_retries": self.num_retries,
            "drop_params": True,  # descarta parâmetros que o provedor não aceita
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:  # noqa: BLE001 — traduzimos para os erros da nossa camada
            raise self._translate(exc) from exc

        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) in {"content_filter", "refusal"}:
            raise LLMRefused("o modelo recusou processar este documento")

        text = choice.message.content or ""
        usage = getattr(response, "usage", None)
        return text, (
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

    @staticmethod
    def _translate(exc: Exception) -> LLMError:
        import litellm

        if isinstance(exc, litellm.RateLimitError):
            return LLMRateLimited("limite de requisições do provedor atingido")
        if isinstance(exc, litellm.ContextWindowExceededError):
            return LLMInputTooLarge("o documento excede a janela de contexto do modelo")
        if isinstance(exc, litellm.ContentPolicyViolationError):
            return LLMRefused("o provedor bloqueou o conteúdo do documento")
        if isinstance(exc, litellm.NotFoundError):
            return LLMModelNotFound(
                "o modelo configurado em LLM_MODEL não existe ou a chave não tem acesso a ele"
            )
        if isinstance(exc, litellm.AuthenticationError):
            return LLMAuthFailed("o provedor recusou a LLM_API_KEY")
        return LLMError(str(exc))
