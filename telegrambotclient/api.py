try:
    import ujson as json
except ImportError:
    import json

import logging
import socket
from io import BytesIO
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import urllib3

from telegrambotclient.base import (InputFile, InputMedia, LabeledPrice,
                                    Message, PassportElementError,
                                    TelegramBotException, TelegramObject,
                                    Update)
from telegrambotclient.utils import exclude_none, pretty_format

logger = logging.getLogger("telegram-bot-client")


class TelegramBotAPIException(TelegramBotException):
    __slots__ = ("_status_code", "_ok", "_error_code", "_description")

    def __init__(self, status_code: int, ok: bool, error_code: int,
                 description: str) -> None:
        super().__init__(description)
        self._status_code = status_code
        self._ok = ok
        self._error_code = error_code
        self._description = description

    @property
    def status_code(self):
        return self._status_code

    @property
    def ok(self):
        return self._ok

    @property
    def error_code(self):
        return self._error_code

    @property
    def description(self):
        return self._description

    def __str__(self) -> str:
        return """
----------------------- TelegramBotAPIException BEGIN-------------------------
status: {0}
ok: {1}
error_code: {2}
description: {3}
----------------------- TelegramBotAPIException END --------------------------
""".format(self.status_code, self.ok, self.error_code, self.description)


class TelegramBotAPICaller:
    __slots__ = ("_pool", )
    _json_header = {"Content-Type": "application/json"}

    def __init__(self,
                 api_host: str = "https://api.telegram.org",
                 maxsize: int = 10,
                 block: bool = True,
                 **other_pool_kwargs):
        other_pool_kwargs.get("headers", {}).update({
            "connection":
            "keep-alive",
            "user-agent":
            "simple-bot: A Telegram Bot API Python Provider",
        })
        other_pool_kwargs["socket_options"] = (
            other_pool_kwargs.get("socket_options", []) +
            urllib3.connection.HTTPConnection.default_socket_options + [
                (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            ])
        if api_host.lower().startswith("https://"):
            self._pool = urllib3.HTTPSConnectionPool(host=api_host[8:],
                                                     maxsize=maxsize,
                                                     block=block,
                                                     **other_pool_kwargs)
        else:
            raise TelegramBotException(
                "Telegram Bot API's URL only supports https://")

    def call(self,
             api_url: str,
             data: Optional[Dict] = None,
             files: Optional[List] = None) -> Any:
        if data is None:
            data = {}
        if not files:
            return self._pool.request(
                "POST",
                api_url,
                body=json.dumps(data).encode("utf-8"),
                headers=self._json_header,
            )
        for _ in files:
            data[_[0]] = _[1]
        return self._pool.request("POST", api_url, fields=data)

    def fetch_file_data(self, file_url: str, chunk_size: int = 128) -> bytes:
        response = self._pool.request("GET", file_url, preload_content=False)
        try:
            if response.status != 200:
                raise TelegramBotException("""
HTTP Status Code: {0}
Reason: {1}""".format(response.status, response.reason))
            with BytesIO() as _:
                for chunk in response.stream(chunk_size):
                    _.write(chunk)
                return _.getvalue()
        finally:
            response.release_conn()


class TelegramBotAPI:

    __version__ = "5.2.1"
    _api_url = "/bot{0}/{1}"
    _download_file_url = "/file/bot{0}/{1}"
    __slots__ = ("_api_caller", )

    def __init__(self, http_request: Optional[TelegramBotAPICaller] = None):
        self._api_caller = http_request or TelegramBotAPICaller()

    @staticmethod
    def __check_response(response):
        if response.status == 500:
            raise TelegramBotException(response.data)
        json_response = json.loads(response.data.decode("utf-8"))
        logger.debug(
            """
----------------------- JSON RESPONSE BEGIN ---------------------------
%s
----------------------- JSON RESPONSE  END  ---------------------------
        """,
            pretty_format(json_response),
        )
        if response.status == 200:
            result = json_response["result"]
            if isinstance(result, dict):
                return TelegramObject(**result)
            return result
        raise TelegramBotAPIException(
            status_code=response.status,
            ok=json_response["ok"],
            error_code=json_response["error_code"],
            description=json_response["description"],
        )

    @staticmethod
    def __prepare_request_data(api_name,
                               **kwargs) -> Tuple[str, Dict, Optional[List]]:
        form_data = exclude_none(**kwargs)
        attached_files = None
        for name, value in form_data.copy().items():
            if isinstance(value, TelegramObject):
                form_data[name] = value.param
                continue
            if isinstance(value, InputFile):
                if attached_files is None:
                    attached_files = []
                if name == "thumb":
                    attached_files.append((value.attach_key, value.file_tuple))
                    form_data["thumb"] = value.attach_str
                else:
                    attached_files.append((name, value.file_tuple))
                    del form_data[name]
        return api_name.replace("_", "").lower(), form_data, attached_files

    def __call_api(
        self,
        token: str,
        api_name: str,
        data: Optional[Dict] = None,
        files: Optional[List] = None,
    ):
        return self.__check_response(
            self._api_caller.call(self._api_url.format(token, api_name), data,
                                  files))

    def __getattr__(self, api_name: str) -> Callable:
        def bot_api_method(token: str, **kwargs):
            real_api_name, form_data, attached_files = self.__prepare_request_data(
                api_name, **kwargs)
            return self.__call_api(token,
                                   real_api_name,
                                   data=form_data,
                                   files=attached_files)

        return bot_api_method

    def get_updates(self, token: str, **kwargs) -> Tuple[Update]:
        if "allowed_updates" in kwargs:
            kwargs["allowed_updates"] = json.dumps(kwargs["allowed_updates"])
        return tuple(
            Update(**raw_update)
            for raw_update in self.getupdates(token, **kwargs))

    def set_webhook(self, token: str, **kwargs) -> bool:
        if "allowed_updates" in kwargs:
            kwargs["allowed_updates"] = json.dumps(kwargs["allowed_updates"])
        return self.setwebhook(token, **kwargs)

    def send_media_group(self, token: str, chat_id: Union[int, str],
                         media: Iterable, **kwargs) -> Message:
        if 2 <= len(media) <= 10:
            files = []
            media_group = []
            for input_media in media:
                if isinstance(input_media, InputMedia):
                    files.extend(input_media.attached_files)
                    media_group.append(input_media.media_data)
            real_api_name, form_data, attached_files = self.__prepare_request_data(
                "sendMediaGroup",
                chat_id=chat_id,
                media=json.dumps(media_group),
                **kwargs)
            return self.__call_api(
                token,
                real_api_name,
                data=form_data,
                files=attached_files + files if attached_files else files,
            )
        raise TelegramBotException("'media' must include 2-10 items")

    def edit_message_media(self,
                           token: str,
                           chat_id: Optional[Union[int, str]] = None,
                           message_id: Optional[int] = None,
                           inline_message_id: Optional[int] = None,
                           media: Optional[InputMedia] = None,
                           **kwargs) -> Message:
        if not media:
            raise TelegramBotException("'media' is required")
        real_api_name, form_data, attached_files = self.__prepare_request_data(
            "editMessageMedia",
            chat_id=chat_id,
            message_id=message_id,
            inline_message_id=inline_message_id,
            media=json.dumps(media.media_data),
            **kwargs)
        return self.__call_api(
            token,
            real_api_name,
            data=form_data,
            files=attached_files +
            media.attached_files if attached_files else media.attached_files,
        )

    def set_my_commands(self, token: str, commands: Iterable) -> bool:
        return self.__call_api(token,
                               "setmycommands",
                               data={"commands": json.dumps(commands)})

    def send_poll(self, token: str, chat_id: Union[int, str], question: str,
                  options: Iterable, **kwargs) -> Message:
        real_api_name, form_data, attached_files = self.__prepare_request_data(
            "sendPoll",
            chat_id=chat_id,
            question=question,
            options=json.dumps(options),
            **kwargs)
        return self.__call_api(token,
                               real_api_name,
                               data=form_data,
                               files=attached_files)

    def answer_inline_query(self, token: str, inline_query_id: str,
                            results: Iterable, **kwargs) -> bool:
        real_api_name, form_data, attached_files = self.__prepare_request_data(
            "answerInlineQuery",
            inline_query_id=inline_query_id,
            results=json.dumps(results),
            **kwargs)
        return self.__call_api(token,
                               real_api_name,
                               data=form_data,
                               files=attached_files)

    def send_invoice(
        self,
        token: str,
        chat_id: int,
        title: str,
        description: str,
        payload: str,
        provider_token: str,
        currency: str,
        prices: Iterable[LabeledPrice],
        **kwargs,
    ) -> Message:
        provider_data = kwargs.get("provider_data", None)
        if provider_data:
            kwargs["provider_data"] = json.dumps(provider_data)
        real_api_name, form_data, attached_files = self.__prepare_request_data(
            "sendInvoice",
            chat_id=chat_id,
            title=title,
            description=description,
            payload=payload,
            provider_token=provider_token,
            currency=currency,
            prices=json.dumps(prices),
            **kwargs)
        return self.__call_api(token,
                               real_api_name,
                               data=form_data,
                               files=attached_files)

    def answer_shipping_query(self,
                              token: str,
                              shipping_query_id: str,
                              ok: bool = True,
                              **kwargs) -> bool:

        if ok:
            if "shipping_options" not in kwargs:
                raise TelegramBotException(
                    "'shipping_options' is required when ok is True")
            kwargs["shipping_options"] = json.dumps(kwargs["shipping_options"])
        else:
            if "error_message" not in kwargs:
                raise TelegramBotException(
                    "'error_message' is required when ok is False")
        real_api_name, form_data, attached_files = self.__prepare_request_data(
            "answerShippingQuery",
            shipping_query_id=shipping_query_id,
            ok=ok,
            **kwargs)
        return self.__call_api(token,
                               real_api_name,
                               data=form_data,
                               files=attached_files)

    def set_passport_data_errors(
            self, token: str, user_id: int,
            errors: Iterable[PassportElementError]) -> bool:
        real_api_name, form_data, attached_files = self.__prepare_request_data(
            "setPassportDataErrors",
            user_id=user_id,
            errors=json.dumps(errors))
        return self.__call_api(token,
                               real_api_name,
                               data=form_data,
                               files=attached_files)

    def get_file_bytes(self, token: str, file_path: str) -> bytes:
        return self._http.fetch_file_data(
            self._download_file_url.format(token, file_path))
