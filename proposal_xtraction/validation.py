"""Regras de consistência sobre a proposta extraída.

Nunca corrigimos os dados — apenas sinalizamos, para que o usuário decida.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Proposta

TOLERANCIA = 0.01

CAMPOS_CABECALHO_ESPERADOS = (
    ("fornecedor", "Fornecedor"),
    ("total_geral", "Total geral"),
    ("data_emissao", "Data de emissão"),
)


@dataclass(frozen=True)
class Aviso:
    campo: str
    mensagem: str
    linha: int | None = None  # índice do item (1-based) quando o aviso é de linha

    def __str__(self) -> str:
        prefixo = f"Item {self.linha}" if self.linha else self.campo
        return f"{prefixo}: {self.mensagem}"


def _fmt(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def checar(proposta: Proposta) -> list[Aviso]:
    avisos: list[Aviso] = []

    if not proposta.itens:
        avisos.append(Aviso("itens", "nenhum item foi identificado no documento"))

    for campo, rotulo in CAMPOS_CABECALHO_ESPERADOS:
        if getattr(proposta, campo) is None:
            avisos.append(Aviso(campo, f"{rotulo} não foi encontrado no documento"))

    avisos.extend(_checar_linhas(proposta))
    avisos.extend(_checar_totais(proposta))
    return avisos


def _checar_linhas(proposta: Proposta) -> list[Aviso]:
    avisos: list[Aviso] = []
    for numero, item in enumerate(proposta.itens, start=1):
        for campo in ("quantidade", "preco_unitario", "valor_total", "desconto"):
            valor = getattr(item, campo)
            if valor is not None and valor < 0:
                avisos.append(Aviso(campo, f"valor negativo ({_fmt(valor)})", linha=numero))

        if item.quantidade is None and item.preco_unitario is None and item.valor_total is None:
            avisos.append(Aviso("valor_total", "linha sem nenhum valor numérico", linha=numero))
            continue

        if item.quantidade is None or item.preco_unitario is None or item.valor_total is None:
            continue

        esperado = item.quantidade * item.preco_unitario - (item.desconto or 0.0)
        if abs(esperado - item.valor_total) > TOLERANCIA:
            avisos.append(
                Aviso(
                    "valor_total",
                    f"qtd × preço unitário − desconto = {_fmt(esperado)}, "
                    f"mas o total da linha é {_fmt(item.valor_total)}",
                    linha=numero,
                )
            )
    return avisos


def _checar_totais(proposta: Proposta) -> list[Aviso]:
    avisos: list[Aviso] = []
    valores = [item.valor_total for item in proposta.itens if item.valor_total is not None]
    if not valores:
        return avisos
    soma = sum(valores)
    faltando = len(proposta.itens) - len(valores)

    if faltando:
        avisos.append(
            Aviso("itens", f"{faltando} item(ns) sem valor total — a soma abaixo é parcial")
        )

    if proposta.subtotal is not None and abs(soma - proposta.subtotal) > TOLERANCIA:
        avisos.append(
            Aviso(
                "subtotal",
                f"soma dos itens é {_fmt(soma)}, mas o subtotal informado é "
                f"{_fmt(proposta.subtotal)}",
            )
        )

    if proposta.total_geral is not None:
        base = proposta.subtotal if proposta.subtotal is not None else soma
        esperado = base + (proposta.frete or 0.0) + (proposta.impostos or 0.0)
        if abs(esperado - proposta.total_geral) > TOLERANCIA:
            avisos.append(
                Aviso(
                    "total_geral",
                    f"subtotal + frete + impostos = {_fmt(esperado)}, mas o total geral "
                    f"informado é {_fmt(proposta.total_geral)}",
                )
            )

    for campo in ("subtotal", "frete", "impostos", "total_geral"):
        valor = getattr(proposta, campo)
        if valor is not None and valor < 0:
            avisos.append(Aviso(campo, f"valor negativo ({_fmt(valor)})"))

    return avisos
