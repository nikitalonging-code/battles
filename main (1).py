import asyncio
import logging

import uvicorn

from app.api import app, bot, _dp
from app.config import settings
from app.database import get_session, init_db
from app.inventory import sync_bank_gifts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_bot():
    await _dp.start_polling(
        bot,
        allowed_updates=["message", "business_connection", "business_message"],
    )


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def run_bank_sync():
    """Фоновый опрос подарков банка → зачисление в инвентарь."""
    interval = max(5, settings.bank_sync_interval)
    if not settings.bank_business_connection_id:
        logger.warning(
            "BANK_BUSINESS_CONNECTION_ID не задан — синхронизация инвентаря отключена"
        )
        return

    logger.info(
        "Bank gift sync started (interval=%ss, connection=%s…)",
        interval,
        settings.bank_business_connection_id[:12],
    )
    while True:
        try:
            async with get_session() as session:
                added = await sync_bank_gifts(session, bot)
                if added:
                    logger.info("Bank sync: +%s gift(s) to inventory", added)
        except Exception:  # noqa: BLE001
            logger.exception("Bank sync loop error")
        await asyncio.sleep(interval)


async def main():
    await init_db()
    await asyncio.gather(run_bot(), run_api(), run_bank_sync())


if __name__ == "__main__":
    asyncio.run(main())
