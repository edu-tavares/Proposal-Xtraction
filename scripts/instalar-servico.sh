#!/usr/bin/env bash
# Deixa o bot rodando em segundo plano, ligando sozinho quando o computador inicia.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

VERDE=$'\033[0;32m'; VERMELHO=$'\033[0;31m'; FIM=$'\033[0m'

if [ ! -x .venv/bin/python ]; then
    echo "${VERMELHO}Rode primeiro: ./scripts/instalar.sh${FIM}"
    exit 1
fi

UNIDADES="$HOME/.config/systemd/user"
mkdir -p "$UNIDADES"

cat > "$UNIDADES/proposal-xtraction.service" <<EOF
[Unit]
Description=Proposal-Xtraction — bot de propostas para Excel
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$RAIZ
ExecStart=$RAIZ/.venv/bin/python $RAIZ/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now proposal-xtraction.service

# Permite que o serviço continue rodando com a sessão fechada.
loginctl enable-linger "$USER" >/dev/null 2>&1 || true

sleep 2
if systemctl --user is-active --quiet proposal-xtraction.service; then
    echo "${VERDE}✓ Bot rodando em segundo plano.${FIM}"
else
    echo "${VERMELHO}✗ O serviço não subiu. Veja o motivo com:${FIM}"
    echo "    journalctl --user -u proposal-xtraction -n 30"
    exit 1
fi

cat <<EOF

Comandos úteis:
  systemctl --user status proposal-xtraction     # ver se está rodando
  systemctl --user restart proposal-xtraction    # reiniciar (depois de mudar o .env)
  systemctl --user stop proposal-xtraction       # desligar
  systemctl --user disable --now proposal-xtraction   # desligar e não ligar mais no boot
  journalctl --user -u proposal-xtraction -f     # acompanhar os logs
EOF
