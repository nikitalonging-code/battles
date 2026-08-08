"""
Инвентарь NFT-подарков в банке.

Депозит:
  Пользователь передаёт уникальный подарок на аккаунт-банк (у которого
  подключён бот как Business-бот). Фоновая задача sync_bank_gifts
  периодически дергает getBusinessAccountGifts и по sender_user
  зачисляет подарок в inventory_items пользователя.

Вывод:
  Пользователь нажимает «Вывести» → transferGift от bank_business_connection_id
  на telegram_id пользователя → статус WITHDRAWN.
"""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import OwnedGiftUnique
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.gifts import transfer_gift
from app.models import InventoryItem, InventoryItemStatus, User

logger = logging.getLogger(__name__)


class InventoryError(Exception):
    pass


def _gift_to_fields(owned: OwnedGiftUnique) -> dict:
    g = owned.gift
    thumb = None
    if g.sticker and g.sticker.thumbnail:
        # file_id — в UI пока не рендерим как картинку без getFile;
        # оставляем на будущее или можно подставить CDN-ссылку маркета
        thumb = g.sticker.thumbnail.file_id

    value = None
    # last_resale_amount в nanoton / stars — в зависимости от API-версии
    raw = getattr(g, "last_resale_amount", None)
    if raw is not None:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None

    return {
        "owned_gift_id": owned.owned_gift_id,
        "gift_name": g.base_name or g.name or "NFT Gift",
        "gift_slug": getattr(g, "slug", None) or getattr(g, "name", None),
        "gift_thumb_url": thumb,
        "gift_value_ton": value,
    }


async def _get_or_create_user_by_tg(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
        await session.flush()
    return user


async def sync_bank_gifts(session: AsyncSession, bot: Bot) -> int:
    """
    Опрашивает подарки банка и зачисляет новые в инвентарь.
    Предпочитает MTProto user-сессию (settings.use_user_bank), иначе Business API.
    """
    if settings.use_user_bank:
        return await _sync_via_user_session(session)

    conn_id = settings.bank_business_connection_id
    if not conn_id:
        return 0

    try:
        result = await bot.get_business_account_gifts(
            business_connection_id=conn_id,
            exclude_unique=False,
            exclude_unlimited=True,
            exclude_saved=False,
            sort_by_price=False,
            limit=100,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("sync_bank_gifts: getBusinessAccountGifts failed: %s", e)
        return 0

    existing = await session.execute(select(InventoryItem.owned_gift_id))
    known_ids = {row[0] for row in existing.all()}

    added = 0
    for owned in result.gifts:
        if not isinstance(owned, OwnedGiftUnique):
            continue
        if not owned.owned_gift_id or owned.owned_gift_id in known_ids:
            continue

        sender = owned.sender_user
        if sender is None:
            logger.info("sync_bank_gifts: gift %s without sender_user, skip", owned.owned_gift_id)
            continue

        user = await _get_or_create_user_by_tg(
            session,
            telegram_id=sender.id,
            username=sender.username,
            first_name=sender.first_name,
        )

        fields = _gift_to_fields(owned)
        item = InventoryItem(
            user_id=user.id,
            status=InventoryItemStatus.AVAILABLE,
            **fields,
        )
        session.add(item)
        known_ids.add(owned.owned_gift_id)
        added += 1
        logger.info(
            "sync_bank_gifts: credited gift %s (%s) to user %s",
            fields["owned_gift_id"],
            fields["gift_name"],
            user.telegram_id,
        )

    if added:
        await session.commit()
    return added


async def _sync_via_user_session(session: AsyncSession) -> int:
    from app.user_bank import list_bank_unique_gifts

    try:
        gifts = await list_bank_unique_gifts()
    except Exception as e:  # noqa: BLE001
        logger.warning("user-bank sync failed: %s", e)
        return 0

    existing = await session.execute(select(InventoryItem.owned_gift_id))
    known_ids = {row[0] for row in existing.all()}

    added = 0
    for g in gifts:
        # owned_gift_id: slug или msg_id как стабильный ключ
        oid = g.get("slug") or (f"msg:{g['msg_id']}" if g.get("msg_id") else None)
        if not oid or oid in known_ids:
            continue
        from_uid = g.get("from_user_id")
        if not from_uid:
            logger.info("user-bank: gift %s without from_user_id, skip", oid)
            continue

        user = await _get_or_create_user_by_tg(session, telegram_id=int(from_uid))
        item = InventoryItem(
            user_id=user.id,
            owned_gift_id=oid,
            gift_name=g.get("name") or "NFT Gift",
            gift_slug=g.get("slug"),
            gift_thumb_url=None,
            gift_value_ton=None,
            status=InventoryItemStatus.AVAILABLE,
        )
        session.add(item)
        known_ids.add(oid)
        added += 1
        logger.info("user-bank: credited %s to user %s", oid, from_uid)

    if added:
        await session.commit()
    return added


async def list_user_inventory(
    session: AsyncSession,
    user: User,
    only_available: bool = True,
) -> list[InventoryItem]:
    q = select(InventoryItem).where(InventoryItem.user_id == user.id)
    if only_available:
        q = q.where(InventoryItem.status == InventoryItemStatus.AVAILABLE)
    q = q.order_by(InventoryItem.deposited_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def withdraw_item(
    session: AsyncSession,
    bot: Bot,
    user: User,
    item_id: int,
) -> InventoryItem:
    """
    Переводит подарок из банка пользователю и помечает как WITHDRAWN.
    """
    conn_id = settings.bank_business_connection_id
    if not settings.use_user_bank and not conn_id:
        raise InventoryError("Банк не настроен (BANK_SESSION или BANK_BUSINESS_CONNECTION_ID)")

    item = await session.get(InventoryItem, item_id)
    if item is None or item.user_id != user.id:
        raise InventoryError("Подарок не найден в вашем инвентаре")
    if item.status != InventoryItemStatus.AVAILABLE:
        raise InventoryError("Этот подарок уже выведен или недоступен")

    try:
        if settings.use_user_bank:
            from app.user_bank import transfer_bank_gift_to_user
            slug = item.gift_slug
            msg_id = None
            if item.owned_gift_id.startswith("msg:"):
                msg_id = int(item.owned_gift_id.split(":", 1)[1])
                slug = None
            await transfer_bank_gift_to_user(
                msg_id=msg_id,
                slug=slug or (item.owned_gift_id if not item.owned_gift_id.startswith("msg:") else None),
                to_telegram_id=user.telegram_id,
            )
        else:
            if not conn_id:
                raise InventoryError("Банк подарков не настроен")
            await transfer_gift(
                bot=bot,
                business_connection_id=conn_id,
                owned_gift_id=item.owned_gift_id,
                new_owner_telegram_id=user.telegram_id,
            )
    except InventoryError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("withdraw_item transfer failed")
        raise InventoryError(f"Не удалось передать подарок: {e}") from e

    item.status = InventoryItemStatus.WITHDRAWN
    item.withdrawn_at = datetime.utcnow()
    await session.commit()
    await session.refresh(item)
    return item


def item_to_dict(item: InventoryItem) -> dict:
    return {
        "id": item.id,
        "owned_gift_id": item.owned_gift_id,
        "name": item.gift_name,
        "slug": item.gift_slug,
        "thumb_url": item.gift_thumb_url,
        "value_ton": item.gift_value_ton,
        "status": item.status.value,
        "deposited_at": item.deposited_at.isoformat() if item.deposited_at else None,
    }
