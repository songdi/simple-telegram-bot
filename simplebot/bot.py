#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import os
from typing import Iterable, Optional, Tuple, Callable
import logging

from simplebot.api import SimpleRequest, TelegramBotAPI
from simplebot.storage import MemoryStorage, SimpleSession, SimpleStorage
from simplebot.base import SimpleBotException, Update, Message, InputFile
from simplebot.utils import build_force_reply_data, parse_force_reply_data, pretty_json

logger = logging.getLogger("simple-bot")


class SimpleBot:
    """SimpleBot."""

    _force_reply_key_format = "bot:force_reply:{0}"
    __slots__ = (
        "_bot_id",
        "_token",
        "_router",
        "_bot_api",
        "_storage",
        "last_update_id",
        "_bot_me",
    )

    def __init__(
        self,
        token: str,
        router,
        storage: Optional[SimpleStorage] = None,
        http_request: Optional[SimpleRequest] = None,
    ):
        """__init__.

        Args:
            token (str): bot token
            router: a SimpleRouter object
            storage (Optional[DefaultStorageBackend]): storage backend
            http_request (Optional[DefaultRequestProvider]): http_request provider
        """
        try:
            self._bot_id = int(token.split(":")[0])
        except IndexError as error:
            raise SimpleBotException("wrong token format: {0}".format(token)) from error
        self._token = token
        self._router = router
        self._bot_api = TelegramBotAPI(
            http_request if isinstance(http_request, SimpleRequest) else SimpleRequest()
        )
        if storage is None:
            logger.warning("You are using a memory storage which can not be persisted.")
        self._storage = storage if isinstance(storage, SimpleStorage) else MemoryStorage()
        self.last_update_id = 0
        self._bot_me = None

    def __getattr__(self, api_name):
        """__getattr__.

        Args:
            api_name: telegram bot api name.
            You can use send_XXX, sendxxx, sendXxx. such as send_message, sendMessage, sendmessage.
        """
        if api_name.startswith("reply"):

            def reply_method(message: Message, **kwargs):
                """reply shotcuts.
                Such as sendMessge, sendPhoto, you can use reply_xxx to reply directly

                Args:
                    message (Message): message sent from the replying user
                    kwargs: other kwargs of sendXXX api method
                """
                kwargs.update(
                    {"chat_id": message.chat.id, "reply_to_message_id": message.message_id}
                )
                return getattr(self._bot_api, "send{0}".format(api_name.split("reply")[1]))(
                    self.token, **kwargs
                )

            return reply_method

        def api_method(**kwargs):
            return getattr(self._bot_api, api_name)(self.token, **kwargs)

        return api_method

    @property
    def token(self) -> str:
        """bot token.

        Args:

        Returns:
            str:
        """
        return self._token

    @property
    def router(self):
        """router in the bot"""
        return self._router

    @property
    def id(self) -> int:
        """bot's id.

        Args:

        Returns:
            int:
        """
        return self._bot_id

    @property
    def me(self):
        """bot's information"""
        if self._bot_me is None:
            self._bot_me = self.get_me()
        return self._bot_me

    async def dispatch(self, update: Update):
        """dispatchu a update.

        Args:
            update (Update): update
        """
        logger.debug(
            """
----------------------- UPDATE BEGIN ---------------------------
%s
----------------------- UPDATE  END  ---------------------------
""",
            pretty_json(update),
        )
        await self._router.route(self, update)

    def join_force_reply(
        self,
        user_id: int,
        callback: Callable,
        force_reply_data: Optional[Iterable[str]] = None,
        expires: int = 1800,
    ):
        """join_force_reply.

        Args:
            user_id (int): user_id
            callback (callable): callback
            force_reply_data (Optional[Iterable[str]]): force_reply_data
            expires (int): expires
        """
        force_reply_callback_name = "{0}.{1}".format(callback.__module__, callback.__name__)
        if not self.router.has_force_reply_handler(force_reply_callback_name):
            raise SimpleBotException(
                "{0} is not a force reply handler".format(force_reply_callback_name)
            )
        field = self._force_reply_key_format.format(user_id)
        session = self.get_session(user_id)
        if force_reply_data is None:
            session.set(field, build_force_reply_data(force_reply_callback_name), expires)
        else:
            session.set(
                field, build_force_reply_data(force_reply_callback_name, *force_reply_data), expires
            )

    def force_reply_done(self, user_id: int):
        """force_reply_done.

        Args:
            user_id (int): user_id
        """
        session = self.get_session(user_id)
        del session[self._force_reply_key_format.format(user_id)]

    def get_force_reply(self, user_id: int) -> Tuple:
        """get_force_reply.

        Args:
            user_id (int): user_id

        Returns:
            Tuple:
        """
        session = self.get_session(user_id)
        force_reply_data = session.get(self._force_reply_key_format.format(user_id))
        if not force_reply_data:
            return None, None
        return parse_force_reply_data(force_reply_data)

    def get_session(self, user_id: int, expires: int = 1800) -> SimpleSession:
        return SimpleSession(self.id, user_id, self._storage, expires)

    def setup_webhook(
        self,
        webhook_url: str,
        certificate: Optional[InputFile] = None,
        max_connections: Optional[int] = None,
        allowed_updates: Optional[Iterable[str]] = None,
        **kwargs
    ) -> bool:
        """set a bot run in webhook model

        Args:
            webhook_url (str): webhook_url
            certificate (Optional[InputFile]): certificate
            max_connections (Optional[int]): max_connections
            allowed_updates (Optional[Iterable[str]]): allowed_updates
            kwargs:

        Returns:
            bool:
        """
        webhook_info = self.get_webhook_info()
        if webhook_info.url != webhook_url:
            self.set_webhook()
            return self.set_webhook(
                url=webhook_url,
                certificate=certificate,
                max_connections=max_connections,
                allowed_updates=allowed_updates,
                **kwargs
            )
        return True

    def download_file(self, src_file_path: str, save_to_file: str):
        """download_file.

        Args:
            src_file_path (str): src_file_path
            save_to_file (str): save_to_file
        """
        file_path = os.path.dirname(save_to_file)
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        file_bytes = self.get_file_bytes(file_path=src_file_path)
        with open(save_to_file, "wb") as new_file:
            new_file.write(file_bytes)

    def run_polling(
        self,
        limit: Optional[int] = None,
        timeout: Optional[int] = None,
        allowed_updates: Optional[Iterable[str]] = None,
        **kwargs
    ):
        """run a bot in long loop model.

        Args:
            get_updates_kwargs: kwargs of telegram bot api 'getUpdates'
        """
        if not timeout:
            logger.warning(
                "Timeout in seconds for long polling. Defaults to 0, i.e. usual short polling. Should be positive, short polling should be used for testing purposes only."
            )
        while True:
            updates = self._bot_api.get_updates(
                self.token,
                offset=self.last_update_id + 1,
                limit=limit,
                timeout=timeout,
                allowed_updates=allowed_updates,
                **kwargs
            )
            if updates:
                self.last_update_id = updates[-1].update_id
                for update in self.get_last_updates(updates):
                    asyncio.run(self.dispatch(update))