from bot import run_bot
from flask_site import run_site
import asyncio

from config_reader import server_enabled

from bot import run_bot
from flask_site import run_site


async def main():
    loop = asyncio.get_event_loop()
    tasks = []

    if server_enabled:
        flask_site = loop.run_in_executor(None, run_site)
        tasks.append(flask_site)

    bot = run_bot()
    tasks.append(bot)

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
