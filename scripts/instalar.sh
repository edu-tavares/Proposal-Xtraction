#!/usr/bin/env bash
# Instalação em um comando: prepara o ambiente Python, instala as dependências,
# cria o .env e um atalho de área de trabalho.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

VERDE=$'\033[0;32m'; AMARELO=$'\033[0;33m'; VERMELHO=$'\033[0;31m'; FIM=$'\033[0m'
ok()    { echo "${VERDE}✓${FIM} $1"; }
aviso() { echo "${AMARELO}!${FIM} $1"; }
erro()  { echo "${VERMELHO}✗${FIM} $1" >&2; }

echo "Instalando o Proposal-Xtraction em $RAIZ"
echo

# --- 1. Encontrar um Python 3.11+ -------------------------------------------
PY=""
for candidato in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidato" >/dev/null 2>&1; then
        if "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            PY="$candidato"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    erro "É necessário Python 3.11 ou mais novo."
    echo
    echo "  Encontrado: $(python3 --version 2>/dev/null || echo 'nenhum python3')"
    echo
    echo "  Para instalar no Ubuntu:"
    echo "    sudo add-apt-repository ppa:deadsnakes/ppa"
    echo "    sudo apt update && sudo apt install python3.12 python3.12-venv"
    echo
    echo "  Depois rode este instalador de novo."
    exit 1
fi
ok "Python encontrado: $($PY --version)"

# --- 2. Ambiente virtual ----------------------------------------------------
if [ ! -d .venv ]; then
    if ! "$PY" -m venv .venv 2>/dev/null; then
        aviso "Falta o pacote de ambientes virtuais do Python. Vou instalar (pede a sua senha)."
        VENV_PKG="${PY#python}-venv"
        sudo apt-get install -y "python3-venv" "python${VENV_PKG}" 2>/dev/null \
            || sudo apt-get install -y python3-venv
        "$PY" -m venv .venv
    fi
    ok "Ambiente virtual criado em .venv/"
else
    ok "Ambiente virtual já existia"
fi

# --- 3. Dependências --------------------------------------------------------
echo "  Instalando dependências (pode levar um ou dois minutos)…"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -e ".[dev]"
ok "Dependências instaladas"

# --- 4. Conferência ---------------------------------------------------------
if ./.venv/bin/python -m pytest -q >/tmp/px-testes.log 2>&1; then
    ok "Testes passaram — a instalação está funcionando"
else
    aviso "Os testes falharam. Detalhes em /tmp/px-testes.log"
    tail -20 /tmp/px-testes.log
fi

# --- 5. Arquivo de configuração --------------------------------------------
if [ ! -f .env ]; then
    cp .env.example .env
    ok "Arquivo .env criado a partir do modelo"
    PRECISA_CONFIGURAR=1
else
    ok "Arquivo .env já existia (não foi alterado)"
    PRECISA_CONFIGURAR=0
fi

# --- 6. Atalho na área de trabalho -----------------------------------------
ATALHOS="$HOME/.local/share/applications"
mkdir -p "$ATALHOS"
cat > "$ATALHOS/proposal-xtraction.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Proposal-Xtraction
Comment=Bot que converte propostas em planilhas Excel
Exec=$RAIZ/scripts/rodar.sh
Path=$RAIZ
Terminal=true
Icon=x-office-spreadsheet
Categories=Office;
EOF
chmod +x "$ATALHOS/proposal-xtraction.desktop"
update-desktop-database "$ATALHOS" >/dev/null 2>&1 || true
ok "Atalho criado — procure por \"Proposal-Xtraction\" no menu de aplicativos"

# --- 7. Próximos passos -----------------------------------------------------
echo
if [ "$PRECISA_CONFIGURAR" = "1" ]; then
    echo "${AMARELO}Falta preencher o arquivo .env com suas chaves.${FIM}"
    echo "Vou abrir o editor agora. Preencha TELEGRAM_BOT_TOKEN e LLM_API_KEY, salve e feche."
    echo
    read -r -p "Pressione Enter para abrir o .env…"
    (xdg-open .env >/dev/null 2>&1 &) || "${EDITOR:-nano}" .env
    echo
fi

echo "Pronto. Para ligar o bot:"
echo "  • pelo menu de aplicativos: procure por ${VERDE}Proposal-Xtraction${FIM}"
echo "  • ou pelo terminal: ${VERDE}./scripts/rodar.sh${FIM}"
echo
echo "Para deixar o bot ligado sempre, mesmo depois de reiniciar o computador:"
echo "  ${VERDE}./scripts/instalar-servico.sh${FIM}"
