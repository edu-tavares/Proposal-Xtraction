from __future__ import annotations

import pytest

from proposal_xtraction.config import Settings
from proposal_xtraction.models import Item, Proposta


@pytest.fixture
def settings() -> Settings:
    return Settings(
        telegram_bot_token="test",
        llm_model="anthropic/claude-opus-5",
        llm_api_key="test",
        max_pages=5,
        pdf_render_dpi=72,
        image_max_dimension=800,
    )


@pytest.fixture
def proposta_ok() -> Proposta:
    return Proposta(
        fornecedor="Metalúrgica Andrade Ltda",
        cnpj="12.345.678/0001-90",
        numero_proposta="PC-2026-0431",
        data_emissao="2026-07-14",
        validade="2026-08-14",
        condicoes_pagamento="30/60 dias",
        prazo_entrega="15 dias úteis",
        moeda="BRL",
        itens=[
            Item(
                codigo="A-100",
                descricao="Chapa de aço 2mm",
                quantidade=10,
                unidade="un",
                preco_unitario=150.0,
                desconto=None,
                valor_total=1500.0,
            ),
            Item(
                codigo="B-220",
                descricao="Perfil U 50x25",
                quantidade=4,
                unidade="m",
                preco_unitario=87.5,
                desconto=50.0,
                valor_total=300.0,
            ),
        ],
        subtotal=1800.0,
        frete=200.0,
        impostos=None,
        total_geral=2000.0,
        observacoes="Instalação não inclusa.",
    )
