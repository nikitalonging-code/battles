import asyncio
from datetime import datetime

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.gifts import transfer_gift
from app.models import Battle, BattleParticipant, BattleStatus, User

DICE_EMOJI = "🎲"


class BattleError(Exception):
    pass


async def _next_battle_number(session: AsyncSession) -> int:
    result = await session.execute(select(func.max(Battle.number)))
    current_max = result.scalar()
    return (current_max or 0) + 1


async def create_battle(
    session: AsyncSession,
    creator: User,
    gift: dict,
    max_participants: int = 3,
) -> Battle:
    if not creator.business_connection_id:
        raise BattleError("Сначала подключите бота как Business-бота, чтобы ставить NFT-подарки.")

    battle = Battle(
        number=await _next_battle_number(session),
        creator_id=creator.id,
        max_participants=max_participants,
        status=BattleStatus.OPEN,
    )
    session.add(battle)
    await session.flush()

    participant = BattleParticipant(
        battle_id=battle.id,
        user_id=creator.id,
        owned_gift_id=gift["owned_gift_id"],
        gift_name=gift["name"],
        gift_slug=gift.get("slug"),
        gift_thumb_url=gift.get("thumb_url"),
        gift_value_ton=gift.get("value_ton"),
        business_connection_id=creator.business_connection_id,
    )
    session.add(participant)
    await session.commit()
    await session.refresh(battle)
    return battle


async def join_battle(
    session: AsyncSession,
    battle: Battle,
    user: User,
    gift: dict,
) -> Battle:
    if not user.business_connection_id:
        raise BattleError("Сначала подключите бота как Business-бота, чтобы ставить NFT-подарки.")
    if battle.status != BattleStatus.OPEN:
        raise BattleError("Эта битва уже недоступна для вступления.")
    if any(p.user_id == user.id for p in battle.participants):
        raise BattleError("Вы уже участвуете в этой битве.")
    if len(battle.participants) >= battle.max_participants:
        raise BattleError("В битве уже нет свободных слотов.")

    participant = BattleParticipant(
        battle_id=battle.id,
        user_id=user.id,
        owned_gift_id=gift["owned_gift_id"],
        gift_name=gift["name"],
        gift_slug=gift.get("slug"),
        gift_thumb_url=gift.get("thumb_url"),
        gift_value_ton=gift.get("value_ton"),
        business_connection_id=user.business_connection_id,
    )
    session.add(participant)
    await session.flush()
    await session.refresh(battle, attribute_names=["participants"])

    if len(battle.participants) >= battle.max_participants:
        battle.status = BattleStatus.RESOLVING

    await session.commit()
    await session.refresh(battle)
    return battle


async def resolve_battle(session: AsyncSession, bot: Bot, battle: Battle) -> Battle:
    """Кидает кубики за каждого участника в канал результатов, определяет победителя
    и переводит подарки проигравших победителю."""
    await session.refresh(battle, attribute_names=["participants"])
    participants = battle.participants

    header = await bot.send_message(
        chat_id=settings.results_channel,
        text=f"⚔️ <b>Битва №{battle.number}</b>\nУчастников: {len(participants)}\nБросаем кубики...",
        parse_mode="HTML",
    )

    # Кидаем кубики по очереди, значение приходит сразу в ответе на send_dice
    rolls: dict[int, int] = {}
    for p in participants:
        msg = await bot.send_dice(chat_id=settings.results_channel, emoji=DICE_EMOJI)
        rolls[p.id] = msg.dice.value
        p.dice_value = msg.dice.value
        await asyncio.sleep(3.5)  # даём анимации кубика доиграть перед следующим броском

    await session.flush()

    # Переброс при ничьей между лидерами
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

    # Передаём подарки проигравших победителю
    winner_user = await session.get(User, winner.user_id)
    results_lines = []
    for p in participants:
        mark = "🏆" if p.id == winner.id else "💀"
        results_lines.append(f"{mark} {p.gift_name} — 🎲 {p.dice_value}")
        if p.id != winner.id:
            try:
                await transfer_gift(
                    bot=bot,
                    business_connection_id=p.business_connection_id,
                    owned_gift_id=p.owned_gift_id,
                    new_owner_telegram_id=winner_user.telegram_id,
                )
                p.gift_transferred = True
            except Exception as e:  # noqa: BLE001
                results_lines.append(f"   ⚠️ не удалось передать подарок автоматически: {e}")

    await bot.send_message(
        chat_id=settings.results_channel,
        text=(
            f"🏆 <b>Битва №{battle.number} завершена!</b>\n\n"
            + "\n".join(results_lines)
            + f"\n\nПобедитель: @{winner_user.username or winner_user.telegram_id}, забирает все подарки."
        ),
        parse_mode="HTML",
    )

    await session.commit()
    await session.refresh(battle)
    return battle
