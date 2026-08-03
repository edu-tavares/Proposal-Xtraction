"""Adapter de canal para Telegram (long polling)."""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path

import structlog
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .. import excel, validation
from ..config import Settings, get_settings
from ..extraction import pipeline
from ..extraction.loader import UnsupportedDocument
from ..llm.base import (
    LLMAuthFailed,
    LLMBadOutput,
    LLMError,
    LLMInputTooLarge,
    LLMModelNotFound,
    LLMRateLimited,
    LLMRefused,
)
from ..llm.factory import get_llm_client
from ..logging_setup import hash_chat_id
from . import messages

log = structlog.get_logger(__name__)

ERROS_CONHECIDOS: list[tuple[type[Exception], str]] = [
    (LLMModelNotFound, messages.ERRO_MODELO_INEXISTENTE),
    (LLMAuthFailed, messages.ERRO_CHAVE_INVALIDA),
    (LLMRateLimited, messages.ERRO_LIMITE_LLM),
    (LLMInputTooLarge, messages.ERRO_DOCUMENTO_GRANDE),
    (LLMRefused, messages.ERRO_RECUSA),
    (LLMBadOutput, messages.ERRO_SAIDA_INVALIDA),
    (UnsupportedDocument, messages.FORMATO_NAO_SUPORTADO),
]


def _nome_saida(nome_entrada: str) -> str:
    base = Path(nome_entrada).stem or "proposta"
    base = re.sub(r"[^\w\-. ]+", "_", base).strip() or "proposta"
    return f"{base[:60]}.xlsx"


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(messages.BOAS_VINDAS)


async def cmd_ajuda(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(messages.AJUDA, parse_mode=ParseMode.HTML)


async def cmd_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    await update.message.reply_text(
        messages.modelo_atual(settings.llm_model, settings.llm_api_base),
        parse_mode=ParseMode.HTML,
    )


async def on_texto(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(messages.NAO_ENTENDI)


async def on_documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fluxo principal: baixa o arquivo, extrai, gera a planilha e devolve."""
    settings: Settings = context.application.bot_data["settings"]
    client = context.application.bot_data["llm_client"]
    message = update.message
    chat_hash = hash_chat_id(message.chat_id)
    iniciado = time.monotonic()

    origem = message.document or (message.photo[-1] if message.photo else None)
    if origem is None:
        await message.reply_text(messages.NAO_ENTENDI)
        return

    tamanho = getattr(origem, "file_size", None) or 0
    limite = settings.max_file_mb * 1024 * 1024
    if tamanho > limite:
        await message.reply_text(
            messages.ARQUIVO_GRANDE.format(
                tamanho=tamanho / 1024 / 1024, limite=settings.max_file_mb
            )
        )
        return

    nome_original = getattr(origem, "file_name", None) or "proposta.jpg"
    aviso = await message.reply_text(messages.PROCESSANDO)
    await context.bot.send_chat_action(message.chat_id, ChatAction.UPLOAD_DOCUMENT)

    with tempfile.TemporaryDirectory(prefix="proposta_") as tmpdir:
        entrada = Path(tmpdir) / Path(nome_original).name
        try:
            arquivo = await context.bot.get_file(origem.file_id)
            await arquivo.download_to_drive(custom_path=str(entrada))

            resultado = await pipeline.extract(entrada, client, settings)
            avisos = validation.checar(resultado.proposta)
            saida = excel.build(
                resultado.proposta, avisos, Path(tmpdir) / _nome_saida(nome_original)
            )

            with saida.open("rb") as fh:
                await message.reply_document(
                    document=fh,
                    filename=saida.name,
                    caption=messages.resumo(
                        nome_arquivo=nome_original,
                        itens=len(resultado.proposta.itens),
                        avisos=avisos,
                        truncado=resultado.truncated,
                        paginas=resultado.pages,
                    ),
                    parse_mode=ParseMode.HTML,
                )

            log.info(
                "documento.processado",
                chat=chat_hash,
                estrategia=resultado.strategy,
                paginas=resultado.pages,
                truncado=resultado.truncated,
                itens=len(resultado.proposta.itens),
                avisos=len(avisos),
                modelo=resultado.model,
                input_tokens=resultado.input_tokens,
                output_tokens=resultado.output_tokens,
                segundos=resultado.elapsed_seconds,
                resultado="ok",
            )
        except Exception as exc:  # noqa: BLE001 — o usuário precisa de resposta sempre
            texto = messages.ERRO_GENERICO
            for tipo, mensagem in ERROS_CONHECIDOS:
                if isinstance(exc, tipo):
                    texto = mensagem
                    break
            log.error(
                "documento.falhou",
                chat=chat_hash,
                erro=type(exc).__name__,
                detalhe=str(exc)[:300],
                modelo=settings.llm_model,
                segundos=round(time.monotonic() - iniciado, 2),
                resultado="erro",
                exc_info=not isinstance(exc, (LLMError, UnsupportedDocument)),
            )
            await message.reply_text(texto, parse_mode=ParseMode.HTML)
        finally:
            try:
                await aviso.delete()
            except Exception:  # noqa: BLE001 — apagar o "Lendo…" é cosmético
                pass


def build_application(settings: Settings | None = None) -> Application:
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não está definido no .env")

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["llm_client"] = get_llm_client(settings)

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ajuda", cmd_ajuda))
    application.add_handler(CommandHandler("help", cmd_ajuda))
    application.add_handler(CommandHandler("modelo", cmd_modelo))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, on_documento))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_texto))
    return application
