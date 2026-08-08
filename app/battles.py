import asyncio
from datetime import datetime

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.gifts import transfer_gift
from app.models import (
    Battle,
    BattleParticipant,
    BattleStatus,
    InventoryItem,
    InventoryItemStatus,
    User,
)

DICE_EMOJI = "🎲"


class BattleError(Exception):
    pass


async def _next_battle_number(session: AsyncSession) -> int:
    result = await session.execute(select(func.max(Battle.number)))
    current_max = result.scalar()
    return (current_max or 0) + 1


async def _stake_inventory_item(
    session: AsyncSession,
    user: User,
    inventory_item_id: int,
) -> InventoryItem:
    """Берёт AVAILABLE-подарок из инвентаря и помечает STAKED."""
    if not settings.bank_business_connection_id:
        raise BattleError("Банк подарков не настроен. Обратитесь к администратору.")

    item = await session.get(InventoryItem, inventory_item_id)
    if item is None or item.user_id != user.id:
        raise BattleError("Подарок не найден в вашем инвентаре")
    if item.status != InventoryItemStatus.AVAILABLE:
        raise BattleError("Этот подарок уже использован или выведен")

    item.status = InventoryItemStatus.STAKED
    await session.flush()
    return item


def _participant_from_item(
    battle_id: int,
    user_id: int,
    item: InventoryItem,
) -> BattleParticipant:
    return BattleParticipant(
        battle_id=battle_id,
        user_id=user_id,
        inventory_item_id=item.id,
        owned_gift_id=item.owned_gift_id,
        gift_name=item.gift_name,
        gift_slug=item.gift_slug,
        gift_thumb_url=item.gift_thumb_url,
        gift_value_ton=item.gift_value_ton,
        business_connection_id=settings.bank_business_connection_id,
    )


async def create_battle(
    session: AsyncSession,
    creator: User,
    inventory_item_id: int,
    max_participants: int = 3,
) -> Battle:
    item = await _stake_inventory_item(session, creator, inventory_item_id)

    battle = Battle(
        number=await _next_battle_number(session),
        creator_id=creator.id,
        max_participants=max_participants,
        status=BattleStatus.OPEN,
    )
    session.add(battle)
    await session.flush()

    session.add(_participant_from_item(battle.id, creator.id, item))
    await session.commit()
    await session.refresh(battle)
    return battle


async def join_battle(
    session: AsyncSession,
    battle: Battle,
    user: User,
    inventory_item_id: int,
) -> Battle:
    if battle.status != BattleStatus.OPEN:
        raise BattleError("Эта битва уже недоступна для вступления.")
    if any(p.user_id == user.id for p in battle.participants):
        raise BattleError("Вы уже участвуете в этой битве.")
    if len(battle.participants) >= battle.max_participants:
        raise BattleError("В битве уже нет свободных слотов.")

    item = await _stake_inventory_item(session, user, inventory_item_id)
    session.add(_participant_from_item(battle.id, user.id, item))
    await session.flush()
    await session.refresh(battle, attribute_names=["participants"])

    if len(battle.participants) >= battle.max_participants:
        battle.status = BattleStatus.RESOLVING

    await session.commit()
    await session.refresh(battle)
    return battle


async def resolve_battle(session: AsyncSession, bot: Bot, battle: Battle) -> Battle:
    """Кубики в канале + transferGift с банка победителю + обновление инвентаря."""
    await session.refresh(battle, attribute_names=["participants"])
    participants = battle.participants
    bank_conn = settings.bank_business_connection_id

    header = await bot.send_message(
        chat_id=settings.results_channel,
        text=f"⚔️ <b>Битва №{battle.number}</b>\nУчастников: {len(participants)}\nБросаем кубики...",
        parse_mode="HTML",
    )

    rolls: dict[int, int] = {}
    for p in participants:
        msg = await bot.send_dice(chat_id=settings.results_channel, emoji=DICE_EMOJI)
        rolls[p.id] = msg.dice.value
        p.dice_value = msg.dice.value
        await asyncio.sleep(3.5)

    await session.flush()

    contenders = participants
    while True:
        best = max(rolls[p.id] for p in contenders)
        leaders = [p for p in contenders if rolls[p.id] == best]
        if len(leaders) == 1:
            winner = leaders[0]
            break
        await bot.send_message(
            chat_id=settings.results_channel,
            text=f"🎲 Ничья между {len(leaders)} игроками — перебрасываем!",
        )
        for p in leaders:
            msg = await bot.send_dice(chat_id=settings.results_channel, emoji=DICE_EMOJI)
            rolls[p.id] = msg.dice.value
            p.dice_value = msg.dice.value
            await asyncio.sleep(3.5)
        contenders = leaders

    battle.winner_participant_id = winner.id
    battle.status = BattleStatus.FINISHED
    battle.resolved_at = datetime.utcnow()
    battle.channel_message_id = header.message_id

    winner_user = await session.get(User, winner.user_id)
    results_lines = []

    for p in participants:
        mark = "🏆" if p.id == winner.id else "💀"
        results_lines.append(f"{mark} {p.gift_name} — 🎲 {p.dice_value}")

        inv = None
        if p.inventory_item_id:
            inv = await session.get(InventoryItem, p.inventory_item_id)

        if p.id == winner.id:
            # Победитель: подарок остаётся на банке, возвращаем в его инвентарь
            if inv:
                inv.status = InventoryItemStatus.AVAILABLE
                inv.user_id = winner_user.id
            continue

        # Проигравший: transfer с банка → победителю в Telegram
        try:
            await transfer_gift(
                bot=bot,
                business_connection_id=bank_conn or p.business_connection_id,
                owned_gift_id=p.owned_gift_id,
                new_owner_telegram_id=winner_user.telegram_id,
            )
            p.gift_transferred = True
            if inv:
                inv.status = InventoryItemStatus.WITHDRAWN
                inv.withdrawn_at = datetime.utcnow()
        except Exception as e:  # noqa: BLE001
            results_lines.append(f"   ⚠️ не удалось передать подарок: {e}")
            # При ошибке вернём стейк проигравшему, чтобы не потерять запись
            if inv and inv.status == InventoryItemStatus.STAKED:
                inv.status = InventoryItemStatus.AVAILABLE

    await bot.send_message(
        chat_id=settings.results_channel,
        text=(
            f"🏆 <b>Битва №{battle.number} завершена!</b>\n\n"
            + "\n".join(results_lines)
            + f"\n\nПобедитель: @{winner_user.username or winner_user.telegram_id}, "
            f"подарки проигравших отправлены на аккаунт."
        ),
        parse_mode="HTML",
    )

    await session.commit()
    await session.refresh(battle)
    return battle
