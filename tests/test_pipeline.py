from __future__ import annotations

import pytest

from proposal_xtraction.extraction import pipeline
from proposal_xtraction.llm.base import ContentPart, LLMResult
from tests.test_loader import pdf_com_texto

PROPOSTA_COM_ITEM = {
    "fornecedor": "ACME",
    "itens": [{"descricao": "Chapa", "quantidade": 2, "preco_unitario": 10.0, "valor_total": 20.0}],
    "total_geral": 20.0,
}
PROPOSTA_VAZIA = {"fornecedor": "ACME", "itens": []}


class FakeLLM:
    """Cliente de LLM que devolve respostas pré-programadas e grava o que recebeu."""

    model = "fake/modelo"

    def __init__(self, respostas: list[dict]):
        self._respostas = list(respostas)
        self.chamadas: list[list[ContentPart]] = []

    async def complete_json(self, system, parts, schema, schema_name="resposta", validator=None):
        self.chamadas.append(parts)
        data = self._respostas.pop(0)
        if validator:
            assert validator(data) == []
        return LLMResult(data=data, model=self.model, input_tokens=10, output_tokens=5)


@pytest.fixture
def pdf_digital(tmp_path):
    return pdf_com_texto(tmp_path / "proposta.pdf")


async def test_extrai_do_texto_nativo_sem_fallback(pdf_digital, settings):
    llm = FakeLLM([PROPOSTA_COM_ITEM])
    resultado = await pipeline.extract(pdf_digital, llm, settings)

    assert resultado.strategy == "texto_nativo"
    assert len(resultado.proposta.itens) == 1
    assert resultado.model == "fake/modelo"
    assert len(llm.chamadas) == 1


async def test_sem_itens_no_texto_faz_fallback_para_imagens(pdf_digital, settings):
    llm = FakeLLM([PROPOSTA_VAZIA, PROPOSTA_COM_ITEM])
    resultado = await pipeline.extract(pdf_digital, llm, settings)

    assert resultado.strategy == "imagens"
    assert len(resultado.proposta.itens) == 1
    assert len(llm.chamadas) == 2
    assert all(p.kind == "image" for p in llm.chamadas[1][1:])


async def test_fallback_nao_repete_indefinidamente(pdf_digital, settings):
    llm = FakeLLM([PROPOSTA_VAZIA, PROPOSTA_VAZIA])
    resultado = await pipeline.extract(pdf_digital, llm, settings)

    assert resultado.proposta.itens == []
    assert len(llm.chamadas) == 2


async def test_instrucao_acompanha_o_conteudo(pdf_digital, settings):
    llm = FakeLLM([PROPOSTA_COM_ITEM])
    await pipeline.extract(pdf_digital, llm, settings)

    primeira = llm.chamadas[0][0]
    assert primeira.kind == "text"
    assert "proposta comercial" in primeira.text


def test_validator_reporta_erro_de_tipo():
    erros = pipeline._validator({"itens": [{"descricao": "X", "quantidade": "muitos"}]})
    assert any("quantidade" in e for e in erros)


def test_validator_aceita_proposta_valida():
    assert pipeline._validator(PROPOSTA_COM_ITEM) == []


def test_validator_rejeita_objeto_aninhado():
    """Sem isso, {"proposta": {...}} validaria como uma proposta vazia."""
    erros = pipeline._validator({"proposta": PROPOSTA_COM_ITEM})
    assert erros and "nível raiz" in erros[0]


def test_validator_rejeita_objeto_sem_relacao_com_o_schema():
    assert pipeline._validator({"foo": 1, "bar": 2})


async def test_resposta_aninhada_do_provedor_nao_perde_os_itens(pdf_digital, settings, monkeypatch):
    """Regressão: o provedor devolveu {"proposta": {...}} e a planilha saiu vazia.

    Exercita o cliente real (não o FakeLLM) para cobrir a normalização que fica
    dentro dele, e não apenas a validação do pipeline.
    """
    import json

    from proposal_xtraction.llm.litellm_client import LiteLLMClient

    cliente = LiteLLMClient(model="fake/modelo")
    monkeypatch.setattr(cliente, "_supports_response_schema", lambda: True)

    async def responde_aninhado(messages, response_format):
        return json.dumps({"proposta": PROPOSTA_COM_ITEM}), (100, 20)

    monkeypatch.setattr(cliente, "_call", responde_aninhado)

    resultado = await pipeline.extract(pdf_digital, cliente, settings)

    assert len(resultado.proposta.itens) == 1
    assert resultado.proposta.fornecedor == "ACME"
