import asyncio
from asyncio.events import TimerHandle
from asyncio.queues import Queue
from asyncio.transports import Transport
from typing import Optional, Callable, Union, Any

from pyhomeworks.exceptions import HomeworksNoCredentialsProvided, InvalidCredentialsProvided, HomeworksConnectionLost

ENCODING = 'ascii'


def ensure_bytes(data: Optional[Union[str, bytes]]):
    if isinstance(data, bytes) or data is None:
        return data

    return data.encode(ENCODING)


class Message:
    def __init__(self, payload: str):
        self.payload = payload


class Command(Message):
    pass


class HomeworksProtocol(asyncio.Protocol):
    _non_login_reply_received_timer: TimerHandle
    read_queue: Queue[Message]
    _transport: Transport

    PROMPT_REQUESTS = [b'LNET> ', b'L232> ']
    LOGIN_REQUEST = b'LOGIN: '
    COMMAND_SEPARATOR = b'\r\n'

    def __init__(self, credentials: Optional[Union[str, bytes]] = None):
        self.ready_future = asyncio.Future()
        self.connection_lost_future = asyncio.Future()
        self.read_queue = Queue()
        self._buffer = b''
        self._credentials = ensure_bytes(credentials)

    def data_received(self, data: bytes) -> None:
        self._buffer += data
        self.handle_buffer_increment()

    def connection_made(self, transport: Transport) -> None:
        self._transport = transport

        self._non_login_reply_received_timer = asyncio.get_event_loop().call_later(0.2, self._notify_ready)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if not self._transport.is_closing():
            self._transport.close()
        self._transport = None
        self._non_login_reply_received_timer.cancel()

        exception = HomeworksConnectionLost(f'Connection lost before ready state: {exc}')
        if not self.ready_future.done():
            self.ready_future.set_exception(exception)

        self.connection_lost_future.set_exception(exception)

    def handle_buffer_increment(self):
        while any([
            self._check_login_prompt(),
            self._trim_prompts(),
            self._check_messages()
        ]):
            pass

    def write(self, data: bytes):
        data = ensure_bytes(data)

        if not self._transport.is_closing():
            self._transport.write(data)

    def _check_login_prompt(self) -> bool:
        return self._trim_prefix(self.LOGIN_REQUEST, self._on_login_prompt_found)

    def _trim_prompts(self) -> bool:
        return any(self._trim_prefix(prompt, self._on_prompt_found) for prompt in self.PROMPT_REQUESTS)

    def _on_prompt_found(self, _):
        self._notify_ready()

    def _on_login_prompt_found(self, _):
        self._non_login_reply_received_timer.cancel()
        if not self._credentials:
            self._raise_exception(HomeworksNoCredentialsProvided())

        self.write(self._credentials + self.COMMAND_SEPARATOR)

    def _trim_prefix(self, prefix: bytes, on_match: Callable[[bytes], None]) -> bool:
        if self._buffer.startswith(prefix):
            self._buffer = self._buffer[len(prefix):]
            on_match(prefix)
            return True

        return False

    def _check_messages(self) -> bool:
        (command, separator, remainder) = self._buffer.partition(self.COMMAND_SEPARATOR)
        if separator != self.COMMAND_SEPARATOR:
            return False
        self._buffer = remainder

        command = command.strip()
        if command == b'':
            return True

        self._handle_message(command.decode(ENCODING))

        return True

    def _handle_message(self, message: str):
        if message == "login successful":
            self._notify_ready()
            return
        elif message == "login incorrect":
            self._raise_exception(InvalidCredentialsProvided())

        self._notify_ready()
        self.read_queue.put_nowait(message)

    def _notify_ready(self):
        self._non_login_reply_received_timer.cancel()
        if self._transport is not None and not self.ready_future.done():
            self.ready_future.set_result(True)

    def _raise_exception(self, exc: Exception):
        if not self.ready_future.done():
            self.ready_future.set_exception(exc)

        raise exc