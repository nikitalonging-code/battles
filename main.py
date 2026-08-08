import asyncio

import uvicorn

from app.api import app, bot, _dp
from app.database import init_db


async def run_bot():
    await _dp.start_polling(bot, allowed_updates=["message", "business_connection", "business_message"])


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await init_db()
    await asyncio.gather(run_bot(), run_api())


if __name__ == "__main__":
    asyncio.run(main())
