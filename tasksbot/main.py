import asyncio
import logging
import os

import aiohttp
from aiotg import run_with_reloader

from tasksbot.bot import bot
from tasksbot.database import db
from tasksbot.reminder import reminder_loop

logger = logging.getLogger(__name__)

DB_URL = os.environ.get('DB_URL', 'postgresql://localhost/tgbot')
AIOHTTP_23 = aiohttp.__version__ > "2.3"


async def bot_loop():
    async with db.with_bind(DB_URL):
        reminder_loop()
        return await bot.loop()


def main():
    from aiomisc.log import basic_config
    debug = True
    basic_config(logging.DEBUG, buffered=True)

    loop = asyncio.get_event_loop()

    # logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

    reload = False
    while True:
        bot_loop_task = asyncio.ensure_future(bot_loop())

        try:
            if reload:
                loop.run_until_complete(run_with_reloader(loop, bot_loop_task, bot.stop))

            else:
                loop.run_until_complete(bot_loop_task)

        # User cancels
        except KeyboardInterrupt:
            logger.debug("User cancelled")
            bot_loop_task.cancel()
            bot.stop()
            break

        # Stop loop
        finally:
            if AIOHTTP_23:
                loop.run_until_complete(bot.session.close())

    logger.debug("Closing loop")
    loop.stop()
    loop.close()


if __name__ == '__main__':
    main()
