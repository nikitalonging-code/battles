import asyncio
import os

import uvicorn

from app.api import app, bot, _dp
from app.database import init_db


async def run_bot():
    await _dp.start_polling(bot, allowed_updates=["message", "business_connection", "business_message"])


async def run_api():
    port = int(os.environ.get("PORT", 8000))  # Render (и другие PaaS) передают порт через $PORT
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await init_db()
    await asyncio.gather(run_bot(), run_api())


if __name__ == "__main__":
    asyncio.run(main())
