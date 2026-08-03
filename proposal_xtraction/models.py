"""Schema fixo da proposta comercial extraída."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Item(BaseModel):
    codigo: str | None = Field(None, description="Código/SKU do item, se houver")
    descricao: str = Field(description="Descrição do item ou serviço")
    quantidade: float | None = Field(None, description="Quantidade")
    unidade: str | None = Field(None, description="Unidade de medida (un, kg, m, h...)")
    preco_unitario: float | None = Field(None, description="Preço unitário")
    desconto: float | None = Field(None, description="Desconto aplicado à linha, em valor")
    valor_total: float | None = Field(None, description="Valor total da linha")


class Proposta(BaseModel):
    fornecedor: str | None = Field(None, description="Razão social ou nome do fornecedor")
    cnpj: str | None = Field(None, description="CNPJ ou CPF do fornecedor")
    numero_proposta: str | None = Field(None, description="Número/identificador da proposta")
    data_emissao: str | None = Field(None, description="Data de emissão em ISO (AAAA-MM-DD)")
    validade: str | None = Field(None, description="Validade da proposta em ISO ou texto")
    condicoes_pagamento: str | None = Field(None, description="Condições de pagamento")
    prazo_entrega: str | None = Field(None, description="Prazo de entrega")
    moeda: str | None = Field(None, description="Código da moeda, ex.: BRL, USD")
    itens: list[Item] = Field(default_factory=list, description="Itens da proposta")
    subtotal: float | None = Field(None, description="Subtotal antes de frete e impostos")
    frete: float | None = Field(None, description="Valor do frete")
    impostos: float | None = Field(None, description="Valor de impostos destacados")
    total_geral: float | None = Field(None, description="Valor total da proposta")
    observacoes: str | None = Field(None, description="Observações relevantes")


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Ajusta o JSON Schema para o formato estrito aceito pela maioria dos provedores.

    Todos os campos entram em `required` (nulos são permitidos pelo próprio tipo) e
    objetos ganham `additionalProperties: false` — é o denominador comum entre
    OpenAI, Gemini e Anthropic para saída estruturada.
    """
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
    for key in ("properties", "$defs"):
        for value in schema.get(key, {}).values():
            if isinstance(value, dict):
                _strictify(value)
    if isinstance(schema.get("items"), dict):
        _strictify(schema["items"])
    for variant in schema.get("anyOf", []):
        if isinstance(variant, dict):
            _strictify(variant)
    return schema


def proposta_json_schema() -> dict[str, Any]:
    """JSON Schema da `Proposta` pronto para ser enviado ao modelo."""
    return _strictify(Proposta.model_json_schema())
