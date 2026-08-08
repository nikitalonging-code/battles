import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Float,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    business_connection_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    business_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    business_rights_ok: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BattleStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVING = "resolving"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class Battle(Base):
    __tablename__ = "battles"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    status: Mapped[BattleStatus] = mapped_column(Enum(BattleStatus), default=BattleStatus.OPEN)

    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    max_participants: Mapped[int] = mapped_column(Integer, default=3)

    channel_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("battle_participants.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])
    participants: Mapped[list["BattleParticipant"]] = relationship(
        back_populates="battle",
        foreign_keys="BattleParticipant.battle_id",
        order_by="BattleParticipant.joined_at",
    )


class BattleParticipant(Base):
    __tablename__ = "battle_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    battle_id: Mapped[int] = mapped_column(ForeignKey("battles.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=True
    )

    owned_gift_id: Mapped[str] = mapped_column(String(128))
    gift_name: Mapped[str] = mapped_column(String(256))
    gift_slug: Mapped[str | None] = mapped_column(String(256), nullable=True)
    gift_thumb_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gift_value_ton: Mapped[float | None] = mapped_column(Float, nullable=True)
    business_connection_id: Mapped[str] = mapped_column(String(128))

    dice_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gift_transferred: Mapped[bool] = mapped_column(Boolean, default=False)

    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    battle: Mapped["Battle"] = relationship(back_populates="participants", foreign_keys=[battle_id])
    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class InventoryItemStatus(str, enum.Enum):
    AVAILABLE = "available"
    WITHDRAWN = "withdrawn"
    STAKED = "staked"


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    owned_gift_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    gift_name: Mapped[str] = mapped_column(String(256))
    gift_slug: Mapped[str | None] = mapped_column(String(256), nullable=True)
    gift_thumb_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gift_value_ton: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[InventoryItemStatus] = mapped_column(
        Enum(InventoryItemStatus), default=InventoryItemStatus.AVAILABLE, index=True
    )

    deposited_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
