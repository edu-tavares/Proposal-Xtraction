"""Entrypoint: sobe o bot do Telegram em long polling."""

from __future__ import annotations

import structlog

from proposal_xtraction.bot.telegram_bot import build_application
from proposal_xtraction.config import get_settings
from proposal_xtraction.logging_setup import setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = structlog.get_logger(__name__)

    application = build_application(settings)
    log.info("bot.iniciando", modelo=settings.llm_model)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
