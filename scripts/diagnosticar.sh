#!/usr/bin/env bash
# Diagnóstico de extração: mostra exatamente o que foi enviado ao modelo e o que ele
# respondeu, sem filtros. Use quando a planilha vier vazia ou errada.
#
#   ./scripts/diagnosticar.sh caminho/da/proposta.pdf
#   ./scripts/diagnosticar.sh proposta.pdf --imagens   # força o caminho de imagem
#   ./scripts/diagnosticar.sh proposta.pdf --debug     # mostra o HTTP da chamada
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$RAIZ/.venv/bin/python" ]; then
    echo "Rode primeiro: ./scripts/instalar.sh" >&2
    exit 1
fi
if [ $# -lt 1 ]; then
    echo "Uso: ./scripts/diagnosticar.sh ARQUIVO.pdf [--imagens] [--texto] [--debug]" >&2
    exit 1
fi

ARQUIVO="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
shift
cd "$RAIZ"

exec .venv/bin/python - "$ARQUIVO" "$@" <<'PYTHON'
import asyncio
import base64
import sys
from pathlib import Path

from proposal_xtraction.config import get_settings
from proposal_xtraction.extraction import loader
from proposal_xtraction.llm.base import ContentPart
from proposal_xtraction.llm.litellm_client import LiteLLMClient, parse_json_loose
from proposal_xtraction.llm.prompts import SYSTEM_PROMPT, USER_INSTRUCTION
from proposal_xtraction.models import Proposta, proposta_json_schema

arquivo = Path(sys.argv[1])
opcoes = sys.argv[2:]
if not arquivo.is_file():
    sys.exit(f"Arquivo não encontrado: {arquivo}")

if "--debug" in opcoes:
    import litellm

    litellm._turn_on_debug()

settings = get_settings()
settings.export_provider_key()
saida = Path("diagnostico")
saida.mkdir(exist_ok=True)

print("=" * 78)
print(f"Arquivo : {arquivo.name} ({arquivo.stat().st_size / 1024:.0f} KB)")
print(f"Modelo  : {settings.llm_model}")
print("=" * 78)

# --- 1. O que o loader produz ------------------------------------------------
if "--imagens" in opcoes:
    doc = loader.load_as_images(arquivo, settings)
elif "--texto" in opcoes:
    texto, paginas = loader.extract_pdf_text(arquivo, settings.max_pages)
    doc = loader.LoadedDocument([ContentPart.from_text(texto)], "texto_nativo", paginas)
else:
    doc = loader.load(arquivo, settings)

print(f"\n[1] LEITURA — estratégia: {doc.strategy}, páginas: {doc.pages}, truncado: {doc.truncated}")

for i, parte in enumerate(doc.parts, 1):
    if parte.kind == "text":
        texto = parte.text or ""
        print(f"    texto: {len(texto)} caracteres")
        print("    ┌─ primeiras 15 linhas do que o modelo recebe " + "─" * 20)
        for linha in texto.splitlines()[:15]:
            print(f"    │ {linha[:90]}")
        print("    └" + "─" * 64)
        (saida / "texto_extraido.txt").write_text(texto)
        print(f"    → texto completo salvo em {saida / 'texto_extraido.txt'}")
    else:
        dados = base64.b64decode(parte.image_b64 or "")
        destino = saida / f"pagina_{i}.png"
        destino.write_bytes(dados)
        print(f"    imagem {i}: {len(dados) // 1024} KB → {destino}")

if doc.strategy == "imagens":
    print("\n    ABRA essas imagens e confira se a proposta está legível.")
    print("    Se estiverem em branco ou ilegíveis, o problema é o documento, não o modelo.")

# --- 2. O que o modelo responde ----------------------------------------------
cliente = LiteLLMClient(
    model=settings.llm_model,
    api_key=settings.llm_api_key,
    api_base=settings.llm_api_base,
    max_output_tokens=settings.llm_max_output_tokens,
    temperature=settings.llm_temperature,
    timeout=settings.llm_timeout_seconds,
    num_retries=0,
)

schema = proposta_json_schema()
usa_schema = cliente._supports_response_schema()
print(f"\n[2] ENVIO — saída estruturada: {'json_schema' if usa_schema else 'json_object'}")
print(f"    visão declarada pelo catálogo: {cliente.supports_vision()}")

mensagens = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {
        "role": "user",
        "content": cliente._to_message_content(
            [ContentPart.from_text(USER_INSTRUCTION), *doc.parts]
        ),
    },
]
if not usa_schema:
    import json as _json

    mensagens[0]["content"] += "\n\nSchema JSON esperado:\n" + _json.dumps(schema, ensure_ascii=False)

try:
    texto, uso = asyncio.run(cliente._call(mensagens, cliente._response_format(schema, "proposta")))
except Exception as exc:
    print(f"\n    ✗ A chamada falhou: {type(exc).__name__}: {exc}")
    sys.exit(1)

print(f"    tokens: entrada={uso[0]} saída={uso[1]}")

print("\n[3] RESPOSTA BRUTA DO MODELO")
print("    ┌" + "─" * 64)
for linha in (texto or "(resposta vazia)").splitlines()[:40]:
    print(f"    │ {linha[:90]}")
print("    └" + "─" * 64)
(saida / "resposta_bruta.txt").write_text(texto or "")

# --- 3. O que sobrevive à validação ------------------------------------------
print("\n[4] INTERPRETAÇÃO")
try:
    dados = parse_json_loose(texto)
except ValueError as exc:
    sys.exit(f"    ✗ Não é JSON válido: {exc}")

try:
    proposta = Proposta.model_validate(dados)
except Exception as exc:
    sys.exit(f"    ✗ JSON não bate com o schema: {exc}")

print(f"    fornecedor .. {proposta.fornecedor}")
print(f"    nº proposta . {proposta.numero_proposta}")
print(f"    total geral . {proposta.total_geral}")
print(f"    itens ....... {len(proposta.itens)}")
for i, item in enumerate(proposta.itens[:5], 1):
    print(f"      {i}. {item.descricao[:50]} | qtd={item.quantidade} | total={item.valor_total}")
if len(proposta.itens) > 5:
    print(f"      … e mais {len(proposta.itens) - 5}")

if not proposta.itens:
    print("\n    Nenhum item extraído. Compare a resposta bruta acima com o documento:")
    print("      • o modelo descreveu o documento mas não achou tabela? → o layout confundiu")
    print("      • o modelo disse que não recebeu imagem? → problema no envio, me avise")
    print("      • a resposta veio vazia? → tente outro modelo em LLM_MODEL")
PYTHON
