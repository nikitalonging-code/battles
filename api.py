from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.battles import BattleError, create_battle, join_battle, resolve_battle
from app.bot import create_bot_and_dispatcher
from app.config import settings
from app.database import get_session, init_db
from app.inventory import (
    InventoryError,
    item_to_dict,
    list_user_inventory,
    withdraw_item,
)
from app.models import Battle, BattleParticipant, BattleStatus, User
from app.telegram_auth import InitDataError, validate_init_data

app = FastAPI(title="NFT Battles API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bot, _dp = create_bot_and_dispatcher()


@app.on_event("startup")
async def startup():
    await init_db()


async def get_current_user(authorization: str = Header(default="")) -> User:
    if not authorization.startswith("tma "):
        raise HTTPException(401, "Нет initData")
    init_data = authorization[4:]
    try:
        parsed = validate_init_data(init_data)
    except InitDataError as e:
        raise HTTPException(401, str(e))

    tg_user = parsed["user"]
    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_user["id"]))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=tg_user["id"],
                username=tg_user.get("username"),
                first_name=tg_user.get("first_name"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


class CreateBattleIn(BaseModel):
    inventory_item_id: int
    max_participants: int = 3


class JoinBattleIn(BaseModel):
    inventory_item_id: int


def _battle_to_dict(battle: Battle) -> dict:
    return {
        "id": battle.id,
        "number": battle.number,
        "status": battle.status.value,
        "max_participants": battle.max_participants,
        "total_value_ton": sum(p.gift_value_ton or 0 for p in battle.participants),
        "channel_message_id": battle.channel_message_id,
        "participants": [
            {
                "user_id": p.user_id,
                "username": p.user.username,
                "avatar_url": p.user.avatar_url,
                "gift_name": p.gift_name,
                "gift_thumb_url": p.gift_thumb_url,
                "gift_value_ton": p.gift_value_ton,
                "dice_value": p.dice_value,
                "is_winner": battle.winner_participant_id == p.id,
            }
            for p in battle.participants
        ],
        "created_at": battle.created_at.isoformat(),
    }


@app.get("/api/config")
async def public_config():
    channel = settings.results_channel.lstrip("@")
    return {
        "results_channel": channel,
        "bank_username": settings.bank_username.lstrip("@") if settings.bank_username else "",
    }


@app.get("/api/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "business_connected": bool(user.business_connection_id and user.business_rights_ok),
    }


@app.get("/api/inventory")
async def inventory_list(user: User = Depends(get_current_user)):
    async with get_session() as session:
        db_user = await session.get(User, user.id)
        items = await list_user_inventory(session, db_user, only_available=True)
        return [item_to_dict(i) for i in items]


@app.post("/api/inventory/{item_id}/withdraw")
async def inventory_withdraw(item_id: int, user: User = Depends(get_current_user)):
    async with get_session() as session:
        db_user = await session.get(User, user.id)
        try:
            item = await withdraw_item(session, bot, db_user, item_id)
        except InventoryError as e:
            raise HTTPException(400, str(e))
        return item_to_dict(item)


@app.get("/api/battles")
async def battles_list(tab: str = "active", user: User = Depends(get_current_user)):
    async with get_session() as session:
        query = select(Battle).options(
            selectinload(Battle.participants).selectinload(BattleParticipant.user)
        )
        if tab == "active":
            query = query.where(Battle.status.in_([BattleStatus.OPEN, BattleStatus.RESOLVING]))
        elif tab == "history":
            query = query.where(Battle.status.in_([BattleStatus.FINISHED, BattleStatus.CANCELLED]))
        elif tab == "mine":
            query = query.where(Battle.participants.any(BattleParticipant.user_id == user.id))
        query = query.order_by(Battle.created_at.desc())
        result = await session.execute(query)
        battles = result.scalars().unique().all()
        return [_battle_to_dict(b) for b in battles]


@app.post("/api/battles")
async def battles_create(payload: CreateBattleIn, user: User = Depends(get_current_user)):
    async with get_session() as session:
        db_user = await session.get(User, user.id)
        try:
            battle = await create_battle(
                session, db_user, payload.inventory_item_id, payload.max_participants
            )
        except BattleError as e:
            raise HTTPException(400, str(e))
        battle = await session.get(
            Battle,
            battle.id,
            options=[selectinload(Battle.participants).selectinload(BattleParticipant.user)],
        )
        return _battle_to_dict(battle)


@app.post("/api/battles/{battle_id}/join")
async def battles_join(battle_id: int, payload: JoinBattleIn, user: User = Depends(get_current_user)):
    async with get_session() as session:
        battle = await session.get(Battle, battle_id, options=[selectinload(Battle.participants)])
        if battle is None:
            raise HTTPException(404, "Битва не найдена")
        db_user = await session.get(User, user.id)
        try:
            battle = await join_battle(session, battle, db_user, payload.inventory_item_id)
        except BattleError as e:
            raise HTTPException(400, str(e))

        if battle.status == BattleStatus.RESOLVING:
            battle = await resolve_battle(session, bot, battle)

        battle = await session.get(
            Battle,
            battle.id,
            options=[selectinload(Battle.participants).selectinload(BattleParticipant.user)],
        )
        return _battle_to_dict(battle)


@app.get("/api/battles/{battle_id}")
async def battle_detail(battle_id: int, user: User = Depends(get_current_user)):
    async with get_session() as session:
        battle = await session.get(
            Battle,
            battle_id,
            options=[selectinload(Battle.participants).selectinload(BattleParticipant.user)],
        )
        if battle is None:
            raise HTTPException(404, "Битва не найдена")
        return _battle_to_dict(battle)


app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
