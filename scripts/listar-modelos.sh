#!/usr/bin/env bash
# Lista os modelos que a SUA chave realmente tem acesso, consultando a API do provedor.
# O catálogo embutido no LiteLLM pode estar desatualizado — esta é a fonte da verdade.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

if [ ! -x .venv/bin/python ]; then
    echo "Rode primeiro: ./scripts/instalar.sh" >&2
    exit 1
fi

exec .venv/bin/python - "$@" <<'PYTHON'
"""Consulta o endpoint de modelos do provedor configurado em LLM_MODEL."""

import sys

import httpx
import litellm

from proposal_xtraction.config import get_settings

# Endpoints de listagem. A maioria dos provedores é compatível com OpenAI.
ENDPOINTS = {
    "groq": ("https://api.groq.com/openai/v1/models", "bearer"),
    "openai": ("https://api.openai.com/v1/models", "bearer"),
    "openrouter": ("https://openrouter.ai/api/v1/models", "bearer"),
    "mistral": ("https://api.mistral.ai/v1/models", "bearer"),
    "deepseek": ("https://api.deepseek.com/models", "bearer"),
    "xai": ("https://api.x.ai/v1/models", "bearer"),
    "together_ai": ("https://api.together.xyz/v1/models", "bearer"),
    "fireworks_ai": ("https://api.fireworks.ai/inference/v1/models", "bearer"),
    "anthropic": ("https://api.anthropic.com/v1/models", "anthropic"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", "query"),
}

settings = get_settings()
provedor = sys.argv[1] if len(sys.argv) > 1 else settings.provider
if not provedor:
    sys.exit("Defina LLM_MODEL no .env como 'provedor/modelo' ou passe o provedor como argumento.")

chave = settings.llm_api_key
base = settings.llm_api_base

if provedor in ENDPOINTS and not base:
    url, auth = ENDPOINTS[provedor]
elif base:  # endpoint próprio (Ollama, vLLM, proxy): assume compatível com OpenAI
    url, auth = base.rstrip("/") + "/models", "bearer"
else:
    sys.exit(
        f"Não sei consultar o provedor '{provedor}' automaticamente.\n"
        "Veja a lista de modelos na documentação dele e escolha um com suporte a imagens."
    )

cabecalhos: dict[str, str] = {}
parametros: dict[str, str] = {}
if auth == "bearer" and chave:
    cabecalhos["Authorization"] = f"Bearer {chave}"
elif auth == "anthropic":
    cabecalhos.update({"x-api-key": chave, "anthropic-version": "2023-06-01"})
elif auth == "query":
    parametros["key"] = chave

print(f"Consultando {url}\n")
try:
    resposta = httpx.get(url, headers=cabecalhos, params=parametros, timeout=30)
except httpx.HTTPError as exc:
    sys.exit(f"Falha de rede ao consultar o provedor: {exc}")

if resposta.status_code in (401, 403):
    sys.exit("O provedor recusou a chave (LLM_API_KEY). Confira o valor no .env.")
if resposta.status_code != 200:
    sys.exit(f"O provedor respondeu {resposta.status_code}: {resposta.text[:300]}")

corpo = resposta.json()
brutos = corpo.get("data") or corpo.get("models") or []
nomes = sorted(
    (m.get("id") or m.get("name", "")).removeprefix("models/") for m in brutos if isinstance(m, dict)
)
if not nomes:
    sys.exit("O provedor não devolveu nenhum modelo.")

atual = settings.llm_model
com_visao, sem_visao, desconhecidos = [], [], []
for nome in nomes:
    completo = f"{provedor}/{nome}"
    try:
        visao = litellm.supports_vision(model=completo)
        (com_visao if visao else sem_visao).append(completo)
    except Exception:
        desconhecidos.append(completo)


def imprimir(titulo: str, itens: list[str]) -> None:
    print(titulo)
    for nome in itens or ["  (nenhum)"]:
        print(f"  {nome}{'   ← em uso' if nome == atual else ''}")
    print()


imprimir("COM suporte a visão — funcionam com foto e PDF escaneado:", com_visao)
imprimir("SEM visão declarada — servem só para PDF com texto selecionável:", sem_visao)
if desconhecidos:
    imprimir("Não catalogados localmente (podem ou não ter visão — teste):", desconhecidos)

print(
    f"Total: {len(nomes)} modelos disponíveis para esta chave.\n"
    "Copie o nome desejado para LLM_MODEL no .env e reinicie o bot.\n"
    "Se um modelo novo aparecer como 'não catalogado', 'pip install -U litellm' atualiza a lista."
)
PYTHON
