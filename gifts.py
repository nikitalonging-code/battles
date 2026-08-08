"""
Всё, что связано с чтением и передачей NFT-подарков через Telegram Business API.

Депозит в битву устроен так:
1. Пользователь один раз подключает бота как Business-бота в настройках
   Telegram (Settings -> Telegram Business -> Chatbots) и выдаёт права
   "Просмотр подарков и звёзд" + "Передача и апгрейд подарков".
2. Бот получает update `business_connection` с business_connection_id,
   мы сохраняем его в User.business_connection_id.
3. Когда игрок хочет застейкать подарок, мини-апп запрашивает у бэкенда
   список его подарков -> бэкенд дергает getBusinessAccountGifts.
4. Игрок физически ничего никому не отправляет: подарок остаётся у него,
   просто в момент вступления в битву мы "замораживаем" его выбор в БД.
5. Когда битва разрешилась, бот вызывает transferGift от business_connection_id
   проигравшего в пользу telegram_id победителя.
"""

from aiogram import Bot
from aiogram.types import OwnedGiftUnique


async def list_unique_gifts(bot: Bot, business_connection_id: str) -> list[dict]:
    """Возвращает список уникальных (NFT) подарков пользователя, доступных для ставки."""
    result = await bot.get_business_account_gifts(
        business_connection_id=business_connection_id,
        exclude_unique=False,
        exclude_unlimited=True,   # обычные лимитированные, не-NFT подарки не участвуют
        exclude_saved=False,
        sort_by_price=True,
    )

    gifts = []
    for owned in result.gifts:
        if not isinstance(owned, OwnedGiftUnique):
            continue
        g = owned.gift
        gifts.append(
            {
                "owned_gift_id": owned.owned_gift_id,
                "name": g.base_name,
                "slug": g.slug,
                "thumb_url": g.sticker.thumbnail.file_id if g.sticker and g.sticker.thumbnail else None,
                # Точной рыночной цены Bot API не отдаёт (это зависит от маркетплейса) —
                # last_resale хранит последнюю известную цену перепродажи, если есть.
                "value_ton": getattr(g, "last_resale_amount", None),
                "transferable": getattr(owned, "can_be_transferred", getattr(owned, "transferable", True)),
            }
        )
    return gifts


async def transfer_gift(
    bot: Bot,
    business_connection_id: str,
    owned_gift_id: str,
    new_owner_telegram_id: int,
) -> bool:
    """Переводит уникальный подарок от проигравшего к победителю. Комиссию в звёздах не берём (0)."""
    return await bot.transfer_gift(
        business_connection_id=business_connection_id,
        owned_gift_id=owned_gift_id,
        new_owner_chat_id=new_owner_telegram_id,
        star_count=0,
    )
