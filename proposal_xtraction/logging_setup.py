"""Logs estruturados em JSON — sem conteúdo do documento nem valores extraídos."""

from __future__ import annotations

import hashlib
import logging

import structlog


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def hash_chat_id(chat_id: int | str) -> str:
    """Identificador estável e não reversível para correlacionar logs."""
    return hashlib.sha256(str(chat_id).encode()).hexdigest()[:12]
