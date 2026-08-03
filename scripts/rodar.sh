#!/usr/bin/env bash
# Liga o bot. Não precisa ativar o ambiente virtual manualmente.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

VERDE=$'\033[0;32m'; VERMELHO=$'\033[0;31m'; FIM=$'\033[0m'

if [ ! -x .venv/bin/python ]; then
    echo "${VERMELHO}A instalação ainda não foi feita.${FIM}"
    echo "Rode primeiro: ./scripts/instalar.sh"
    read -r -p "Pressione Enter para fechar…"
    exit 1
fi

if [ ! -f .env ]; then
    echo "${VERMELHO}Falta o arquivo .env.${FIM}"
    echo "Rode: ./scripts/instalar.sh"
    read -r -p "Pressione Enter para fechar…"
    exit 1
fi

if ! grep -qE '^TELEGRAM_BOT_TOKEN=.+' .env; then
    echo "${VERMELHO}O TELEGRAM_BOT_TOKEN está vazio no arquivo .env.${FIM}"
    echo "Pegue o token com o @BotFather no Telegram e preencha o .env."
    read -r -p "Pressione Enter para abrir o .env…"
    (xdg-open .env >/dev/null 2>&1 &) || "${EDITOR:-nano}" .env
    exit 1
fi

if ! grep -qE '^LLM_API_KEY=.+' .env && ! grep -qE '^LLM_API_BASE=.+' .env; then
    echo "${VERMELHO}A LLM_API_KEY está vazia no arquivo .env.${FIM}"
    echo "Preencha a chave do provedor escolhido (ou use LLM_API_BASE para um modelo local)."
    read -r -p "Pressione Enter para abrir o .env…"
    (xdg-open .env >/dev/null 2>&1 &) || "${EDITOR:-nano}" .env
    exit 1
fi

echo "${VERDE}Bot ligado.${FIM} Envie uma proposta para ele no Telegram."
echo "Para desligar, feche esta janela ou pressione Ctrl+C."
echo

trap 'echo; echo "Bot desligado."; exit 0' INT TERM
exec .venv/bin/python main.py
