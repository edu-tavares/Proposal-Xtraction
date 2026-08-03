from __future__ import annotations

from proposal_xtraction.models import Item, Proposta
from proposal_xtraction.validation import checar


def campos(avisos) -> set[str]:
    return {a.campo for a in avisos}


def test_proposta_consistente_nao_gera_avisos(proposta_ok):
    assert checar(proposta_ok) == []


def test_linha_com_total_inconsistente(proposta_ok):
    proposta_ok.itens[0].valor_total = 1400.0  # deveria ser 1500
    avisos = checar(proposta_ok)
    linha = [a for a in avisos if a.linha == 1]
    assert linha and "1.500,00" in linha[0].mensagem


def test_desconto_entra_no_calculo_da_linha():
    proposta = Proposta(
        itens=[
            Item(
                descricao="X", quantidade=2, preco_unitario=100.0, desconto=30.0, valor_total=170.0
            )
        ]
    )
    assert not [a for a in checar(proposta) if a.linha == 1]


def test_soma_dos_itens_diverge_do_subtotal(proposta_ok):
    proposta_ok.subtotal = 1900.0
    assert "subtotal" in campos(checar(proposta_ok))


def test_total_geral_diverge_de_subtotal_mais_frete(proposta_ok):
    proposta_ok.total_geral = 2500.0
    assert "total_geral" in campos(checar(proposta_ok))


def test_campos_de_cabecalho_ausentes():
    avisos = checar(Proposta(itens=[Item(descricao="X", valor_total=10.0)]))
    assert {"fornecedor", "total_geral", "data_emissao"} <= campos(avisos)


def test_proposta_sem_itens():
    avisos = checar(Proposta())
    assert any(a.campo == "itens" and "nenhum item" in a.mensagem for a in avisos)


def test_valor_negativo_em_item():
    proposta = Proposta(itens=[Item(descricao="X", quantidade=-1, valor_total=-10.0)])
    negativos = [a for a in checar(proposta) if "negativo" in a.mensagem]
    assert len(negativos) == 2


def test_item_sem_nenhum_valor_numerico():
    proposta = Proposta(itens=[Item(descricao="Serviço a combinar")])
    assert any("sem nenhum valor numérico" in a.mensagem for a in checar(proposta))


def test_soma_parcial_quando_falta_valor_em_item(proposta_ok):
    proposta_ok.itens[1].valor_total = None
    proposta_ok.subtotal = 1500.0
    mensagens = [a.mensagem for a in checar(proposta_ok)]
    assert any("soma abaixo é parcial" in m for m in mensagens)
