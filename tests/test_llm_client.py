"""Testa a implementação LiteLLM sem tocar em rede: `litellm.acompletion` é substituído."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from proposal_xtraction.llm.base import (
    ContentPart,
    LLMAuthFailed,
    LLMBadOutput,
    LLMError,
    LLMInputTooLarge,
    LLMModelNotFound,
    LLMRateLimited,
)
from proposal_xtraction.llm.litellm_client import LiteLLMClient, parse_json_loose

SCHEMA = {"type": "object", "properties": {"nome": {"type": "string"}}}


def resposta(texto: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=texto), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
    )


@pytest.fixture
def client(monkeypatch):
    cliente = LiteLLMClient(model="fake/modelo", api_key="k")
    monkeypatch.setattr(cliente, "_supports_response_schema", lambda: True)
    return cliente


def instalar_respostas(monkeypatch, client, textos: list[str]) -> list[dict]:
    """Faz `_call` devolver `textos` em sequência e registra as chamadas."""
    chamadas: list[dict] = []
    fila = list(textos)

    async def fake_call(messages, response_format):
        chamadas.append({"messages": [dict(m) for m in messages], "format": response_format})
        return fila.pop(0), (100, 20)

    monkeypatch.setattr(client, "_call", fake_call)
    return chamadas


# -- parse_json_loose --------------------------------------------------------


def test_parse_aceita_json_puro():
    assert parse_json_loose('{"a": 1}') == {"a": 1}


def test_parse_remove_cerca_de_codigo():
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_recorta_json_com_texto_ao_redor():
    assert parse_json_loose('Segue o resultado:\n{"a": 1}\nEspero ter ajudado.') == {"a": 1}


def test_parse_rejeita_resposta_vazia():
    with pytest.raises(ValueError):
        parse_json_loose("   ")


def test_parse_rejeita_lista_no_topo():
    with pytest.raises(ValueError, match="objeto JSON"):
        parse_json_loose("[1, 2, 3]")


# -- complete_json -----------------------------------------------------------


async def test_json_valido_na_primeira_tentativa(monkeypatch, client):
    chamadas = instalar_respostas(monkeypatch, client, ['{"nome": "ACME"}'])
    resultado = await client.complete_json("sys", [ContentPart.from_text("oi")], SCHEMA)

    assert resultado.data == {"nome": "ACME"}
    assert resultado.model == "fake/modelo"
    assert resultado.input_tokens == 100
    assert len(chamadas) == 1


async def test_json_malformado_dispara_uma_correcao(monkeypatch, client):
    chamadas = instalar_respostas(monkeypatch, client, ["não sei responder", '{"nome": "ACME"}'])
    resultado = await client.complete_json("sys", [ContentPart.from_text("oi")], SCHEMA)

    assert resultado.data == {"nome": "ACME"}
    assert len(chamadas) == 2
    assert "rejeitado na validação" in chamadas[1]["messages"][-1]["content"]


async def test_erro_de_validacao_volta_para_o_modelo(monkeypatch, client):
    chamadas = instalar_respostas(monkeypatch, client, ['{"nome": 1}', '{"nome": "ACME"}'])

    def validator(data):
        return [] if isinstance(data.get("nome"), str) else ["nome: deve ser texto"]

    resultado = await client.complete_json(
        "sys", [ContentPart.from_text("oi")], SCHEMA, validator=validator
    )

    assert resultado.data == {"nome": "ACME"}
    assert "nome: deve ser texto" in chamadas[1]["messages"][-1]["content"]


async def test_desiste_apos_a_segunda_falha(monkeypatch, client):
    chamadas = instalar_respostas(monkeypatch, client, ["lixo", "mais lixo"])
    with pytest.raises(LLMBadOutput):
        await client.complete_json("sys", [ContentPart.from_text("oi")], SCHEMA)
    assert len(chamadas) == 2


async def test_schema_vai_no_prompt_quando_provedor_nao_suporta(monkeypatch, client):
    monkeypatch.setattr(client, "_supports_response_schema", lambda: False)
    chamadas = instalar_respostas(monkeypatch, client, ['{"nome": "ACME"}'])
    await client.complete_json("sys", [ContentPart.from_text("oi")], SCHEMA)

    assert chamadas[0]["format"] == {"type": "json_object"}
    assert "Schema JSON esperado" in chamadas[0]["messages"][0]["content"]


# -- conversão de conteúdo ---------------------------------------------------


def test_imagem_vira_data_uri(client):
    parte = ContentPart.from_image_bytes(b"\x89PNG", "image/png")
    conteudo = client._to_message_content([ContentPart.from_text("texto"), parte])

    assert conteudo[0] == {"type": "text", "text": "texto"}
    assert conteudo[1]["type"] == "image_url"
    assert conteudo[1]["image_url"]["url"].startswith("data:image/png;base64,")


# -- tradução de erros do provedor -------------------------------------------


@pytest.mark.parametrize(
    ("excecao_litellm", "esperado"),
    [
        ("NotFoundError", LLMModelNotFound),
        ("AuthenticationError", LLMAuthFailed),
        ("RateLimitError", LLMRateLimited),
        ("ContextWindowExceededError", LLMInputTooLarge),
    ],
)
def test_erros_do_provedor_viram_erros_da_nossa_camada(excecao_litellm, esperado):
    """Um modelo inexistente precisa virar mensagem acionável, não erro genérico."""
    import litellm

    tipo = getattr(litellm, excecao_litellm)
    exc = tipo.__new__(tipo)  # as assinaturas variam; só o tipo importa aqui
    assert isinstance(LiteLLMClient._translate(exc), esperado)


def test_erro_desconhecido_vira_erro_generico():
    assert type(LiteLLMClient._translate(ValueError("algo inesperado"))) is LLMError


def test_json_schema_e_enviado_como_response_format(client):
    formato = client._response_format(SCHEMA, "proposta")
    assert formato["type"] == "json_schema"
    assert formato["json_schema"]["name"] == "proposta"
    assert json.dumps(formato["json_schema"]["schema"]) == json.dumps(SCHEMA)
