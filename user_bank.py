"""
Работа с NFT-подарками через MTProto-сессию аккаунта-банка (Telethon).
Обходит временное ограничение Telegram на gifts у Business-ботов.

Нужны: API_ID, API_HASH, BANK_SESSION (StringSession строки банка).
Сессию один раз получить локально (см. README / скрипт ниже).
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _telethon_available() -> bool:
    try:
        import telethon  # noqa: F401
        return True
    except ImportError:
        return False


async def get_bank_client():
    """Ленивый singleton TelegramClient для аккаунта-банка."""
    global _client
    if _client is not None:
        return _client

    if not settings.api_id or not settings.api_hash or not settings.bank_session:
        raise RuntimeError(
            "Для user-bank нужны API_ID, API_HASH и BANK_SESSION в Environment"
        )

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    _client = TelegramClient(
        StringSession(settings.bank_session),
        int(settings.api_id),
        settings.api_hash,
    )
    await _client.connect()
    if not await _client.is_user_authorized():
        raise RuntimeError("BANK_SESSION невалидна или не авторизована")
    me = await _client.get_me()
    logger.info("Bank user session OK: @%s id=%s", me.username, me.id)
    return _client


async def list_bank_unique_gifts() -> list[dict[str, Any]]:
    """
    Список уникальных (collectible) подарков на аккаунте-банке.
    Возвращает dict с msg_id / saved_id / slug / name / from_user_id.
    """
    from telethon.tl.functions.payments import GetSavedStarGiftsRequest
    from telethon.tl.types import InputPeerSelf

    client = await get_bank_client()
    gifts: list[dict] = []
    offset = ""

    while True:
        result = await client(
            GetSavedStarGiftsRequest(
                peer=InputPeerSelf(),
                offset=offset,
                limit=100,
                exclude_unique=False,
                exclude_unlimited=True,
                exclude_unsaved=False,
                exclude_saved=False,
            )
        )
        for g in result.gifts:
            # Unique / collectible
            gift_obj = getattr(g, "gift", None)
            if gift_obj is None:
                continue
            # starGiftUnique имеет slug / num / title
            slug = getattr(gift_obj, "slug", None)
            title = getattr(gift_obj, "title", None) or getattr(gift_obj, "base_name", None)
            if not slug and not getattr(gift_obj, "num", None):
                # не unique
                continue

            from_id = None
            peer = getattr(g, "from_id", None)
            if peer is not None:
                from_id = getattr(peer, "user_id", None)

            gifts.append(
                {
                    "msg_id": getattr(g, "msg_id", None),
                    "saved_id": getattr(g, "saved_id", None),
                    "slug": slug,
                    "name": title or slug or "NFT Gift",
                    "from_user_id": from_id,
                    "transfer_stars": getattr(g, "transfer_stars", None) or 0,
                    "date": getattr(g, "date", None),
                }
            )

        offset = getattr(result, "next_offset", None) or ""
        if not offset:
            break

    return gifts


async def transfer_bank_gift_to_user(
    *,
    msg_id: int | None,
    slug: str | None,
    to_telegram_id: int,
) -> bool:
    """
    Передаёт unique-подарок с банка пользователю.
    Бесплатный transfer → payments.transferStarGift;
    платный → invoice + SendStarsForm.
    """
    from telethon.tl.functions.payments import (
        GetPaymentFormRequest,
        SendStarsFormRequest,
        TransferStarGiftRequest,
    )
    from telethon.tl.types import (
        InputInvoiceStarGiftTransfer,
        InputPeerUser,
        InputSavedStarGiftSlug,
        InputSavedStarGiftUser,
        InputUser,
    )

    client = await get_bank_client()
    entity = await client.get_entity(to_telegram_id)
    to_peer = InputPeerUser(user_id=entity.id, access_hash=entity.access_hash)

    if slug:
        stargift = InputSavedStarGiftSlug(slug=slug)
    elif msg_id:
        stargift = InputSavedStarGiftUser(msg_id=msg_id)
    else:
        raise ValueError("Нужен msg_id или slug подарка")

    try:
        await client(TransferStarGiftRequest(stargift=stargift, to_id=to_peer))
        logger.info("transferStarGift OK → %s (slug=%s msg_id=%s)", to_telegram_id, slug, msg_id)
        return True
    except Exception as e:
        err = str(e)
        # PAYMENT_REQUIRED — платный transfer
        if "PAYMENT_REQUIRED" not in err and "payment" not in err.lower():
            logger.exception("transferStarGift failed")
            raise

    # Платный путь
    invoice = InputInvoiceStarGiftTransfer(
        stargift=stargift,
        to_id=InputUser(user_id=entity.id, access_hash=entity.access_hash),
    )
    form = await client(GetPaymentFormRequest(invoice=invoice))
    await client(SendStarsFormRequest(form_id=form.form_id, invoice=invoice))
    logger.info("paid transfer OK → %s", to_telegram_id)
    return True
