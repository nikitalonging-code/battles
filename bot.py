import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    BusinessConnection,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy import select

from app.config import settings
from app.database import get_session
from app.models import User

logger = logging.getLogger(__name__)
router = Router()


async def get_or_create_user(session, tg_user) -> User:
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@router.message(CommandStart())
async def start(message: Message):
    async with get_session() as session:
        await get_or_create_user(session, message.from_user)

    bank = settings.bank_username.lstrip("@") if settings.bank_username else ""
    deposit_line = (
        f"\n\nЧтобы играть: отправьте NFT-подарок на @{bank} — он появится в инвентаре мини-аппа."
        if bank
        else "\n\nЧтобы играть: отправьте NFT-подарок на аккаунт-банк — он появится в инвентаре."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚔️ Открыть битвы", web_app=WebAppInfo(url=settings.webapp_url))]
        ]
    )
    await message.answer(
        "Привет! Здесь можно устраивать битвы на NFT-подарки."
        + deposit_line
        + "\n\nBusiness-подключение игрокам не нужно — подарки стейкаются из инвентаря.",
        reply_markup=kb,
    )


@router.business_connection()
async def on_business_connection(connection: BusinessConnection):
    """
    Логируем connection.id — его нужно прописать в BANK_BUSINESS_CONNECTION_ID
    для аккаунта-банка.
    """
    logger.info(
        "business_connection: id=%s user_id=%s username=%s enabled=%s",
        connection.id,
        connection.user.id,
        connection.user.username,
        connection.is_enabled,
    )
    # Явно печатаем, чтобы было видно в консоли при настройке банка
    print(
        f"\n>>> BUSINESS CONNECTION ID: {connection.id}\n"
        f">>> user: @{connection.user.username} ({connection.user.id}) "
        f"enabled={connection.is_enabled}\n"
    )

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == connection.user.id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=connection.user.id, username=connection.user.username)
            session.add(user)

        if connection.is_enabled:
            rights = connection.rights
            ok = bool(
                rights
                and getattr(rights, "can_view_gifts_and_stars", False)
                and getattr(rights, "can_transfer_and_upgrade_gifts", False)
            )
            user.business_connection_id = connection.id
            user.business_connected_at = datetime.utcnow()
            user.business_rights_ok = ok
            if not ok:
                logger.warning(
                    "Business connection %s: недостаточно прав (нужны view gifts + transfer gifts)",
                    connection.id,
                )
        else:
            user.business_connection_id = None
            user.business_rights_ok = False

        await session.commit()


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    return bot, dp
