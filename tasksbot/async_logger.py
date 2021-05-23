import asyncio
import logging
from functools import partial


class ToAsync:
    def __init__(self, sync_logger):
        self._logger = sync_logger
        self.loop = asyncio.get_event_loop()

    def __getattr__(self, item):
        if not hasattr(self._logger, item):
            super().__getattr__(item)

        attr = getattr(self._logger, item)
        if not callable(attr):
            return attr
        # result of calling can be awaitable or not - anyway it starts doing action an "backgroud".
        #  if need result of that action or need to wait when action has been done - use "await"
        #  if don't need wait when action done - can call without await
        async_method = lambda *args, **kwargs: self.loop.run_in_executor(None, partial(
            self._logger.info, *args, **kwargs))

        setattr(self, item, async_method)
        return async_method


def get_async_logger(name):
    logger = logging.getLogger(name)
    return ToAsync(logger)
