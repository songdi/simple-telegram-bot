import logging
import sys
from typing import Iterable, Optional, Dict

from simplebot.api import SimpleRequest
from simplebot.base import SimpleBotException, Update
from simplebot.bot import SimpleBot
from simplebot.router import SimpleRouter
from simplebot.storage import SimpleStorage
from simplebot.handler import UpdateHandler

logger = logging.getLogger("simple-bot")
formatter = logging.Formatter('%(levelname)s %(asctime)s (%(filename)s:%(lineno)d): "%(message)s"')
console_output_handler = logging.StreamHandler(sys.stderr)
console_output_handler.setFormatter(formatter)
logger.addHandler(console_output_handler)
logger.setLevel(logging.INFO)


class BotProxy:
    """
    A bots and routers manager and updates dispatcher
    Attributes:
        _bot_data: a dict for saving bots
        _router_data: a dict for saving routers
        router: a function for creating a router
        _name: this proxy's name

    """

    __slots__ = ("_bot_data", "_router_data", "_name")

    def __init__(self, name: str = "default_proxy") -> None:
        """__init__.

        Args:
            name (str): name of this bot proxy

        Returns:
            None:
        """
        super().__init__()
        self._bot_data = {}
        self._router_data = {}
        self._name = name

    @property
    def name(self):
        """name."""
        return self._name

    def router(
        self,
        name: Optional[str] = None,
        handlers: Optional[Iterable[UpdateHandler]] = None,
    ) -> SimpleRouter:
        """create a router or return the router if this name exists.

        Args:
            name: this router's name
            handlers: handlers in this router

        Returns:
            A SimpleRouter object

        """
        name = name or "default_router"
        if name not in self._router_data:
            self._router_data[name] = SimpleRouter(name, handlers)
        return self._router_data[name]

    def create_bot(
        self,
        token: str,
        router: Optional[SimpleRouter] = None,
        handlers: Optional[Iterable[UpdateHandler]] = None,
        storage: Optional[SimpleStorage] = None,
        api_host: Optional[str] = None,
        **urllib3_pool_kwargs
    ) -> SimpleBot:
        """create a bot

        Args:
            token: bot's token
            router: router that will put in this bot. If router is None, handlers will be used for creating a router
            handlers: if router is None, handlers will add onto this bot
            storage: a persisted storage backend
            api_host: new telegram bot api host if not use the official api host: https://api.telegram.org
            urllib3_pool_kwargs: https connection pool kwargs of urllib3
        Returns:
            A SimpleBot object

        """
        if token in self._bot_data:
            del self._bot_data[token]
        router = router or self.router(handlers=handlers)
        self._bot_data[token] = SimpleBot(
            token,
            router,
            storage,
            SimpleRequest(api_host=api_host or "https://api.telegram.org", **urllib3_pool_kwargs),
        )
        return self._bot_data[token]

    async def dispatch(self, token: str, raw_update: Dict):
        """dispatch a incoming update to a bot

        Args:
            token (str): telegram bot token
            raw_update (Dict): a incoming update
        """
        simple_bot = self._bot_data.get(token, None)
        if simple_bot is None:
            raise SimpleBotException("No bot found with token[ secret ]: '{0}'".format(token))
        await simple_bot.dispatch(Update(**raw_update))


# default bot proxy
bot_proxy = BotProxy()