"""Entrypoint: sobe o bot do Telegram em long polling."""

from __future__ import annotations

import sys

import structlog
from telegram.error import InvalidToken, NetworkError

from proposal_xtraction.bot.telegram_bot import build_application
from proposal_xtraction.config import get_settings
from proposal_xtraction.logging_setup import setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = structlog.get_logger(__name__)

    try:
        application = build_application(settings)
        log.info("bot.iniciando", modelo=settings.llm_model)
        application.run_polling(drop_pending_updates=True)
    except InvalidToken:
        sys.exit(
            "\nO TELEGRAM_BOT_TOKEN do arquivo .env não é válido.\n"
            "Peça um novo ao @BotFather no Telegram e cole no .env "
            "(formato: 1234567890:AAH...).\n"
        )
    except NetworkError as exc:
        sys.exit(
            f"\nNão consegui falar com o Telegram: {exc}\n"
            "Verifique sua conexão com a internet e tente de novo.\n"
        )
    except RuntimeError as exc:
        sys.exit(f"\n{exc}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
