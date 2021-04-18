import logging
import queue
from enum import IntEnum
from threading import Thread

logger = logging.getLogger('mock_homeworks_device')


class HomeworksDevice(Thread):
    class State(IntEnum):
        START = 0
        LOGIN_REQUEST_SENT = 1
        CONNECTED = 2

    def __init__(self, on_send=lambda x: print(x), command_separator=b'\r\n'):
        Thread.__init__(self)
        self._receive_queue = queue.SimpleQueue()
        self._receive_buffer = b''

        self._command_separator = command_separator
        self._on_send = on_send
        self.require_login = False
        self.send_prompts = True

        self.state = self.State.START

    def send(self, data: bytes, line_ending=True) -> None:
        if line_ending:
            data += self._command_separator
        logger.debug(f"send: {data}")
        self._on_send(data)

    def receive(self, data: bytes) -> None:
        logger.debug(f"receive: {data}")
        self._receive_queue.put_nowait(data)

    def run(self) -> None:
        while True:
            if self.require_login:
                if self.state == self.State.START:
                    self.send(b'LOGIN: ', line_ending=False)
                    self.state = self.State.LOGIN_REQUEST_SENT
            else:
                self.state = self.State.CONNECTED

            buf = self._receive_queue.get()
            if buf is None:
                return
            self._receive_buffer += buf

            self.handle_buffer_increment()

    def stop(self):
        self._receive_queue.put_nowait(None)

    def handle_buffer_increment(self):
        while True:
            (message, separator, remainder) = self._receive_buffer.partition(self._command_separator)
            if separator != self._command_separator:
                return
            self._receive_buffer = remainder

            if self.state == self.State.LOGIN_REQUEST_SENT:
                if not self.handle_login_credentials(message):
                    return

            if self.state == self.State.CONNECTED:
                self.handle_command(message)

    def handle_command(self, command):
        if command.rstrip() == b'PROMPTOFF':
            self.send_prompts = False
        if command.rstrip() == b'KBMON':
            self.send(b'Keypad button monitoring enabled')
        elif command.rstrip() == b'GSMON':
            self.send(b'GrafikEye scene monitoring enabled')
        elif command.rstrip() == b'DLMON':
            self.send(b'Dimmer level monitoring enabled')
        elif command.rstrip() == b'KLMON':
            self.send(b'Keypad led monitoring enabled')
        if self.send_prompts:
            self.send(b'LNET> ', line_ending=False)

    def handle_login_credentials(self, message) -> bool:
        if message == b'user,password':
            self.state = self.State.CONNECTED
            self.send(b'login successful')
            return True
        else:
            self.send(b'login incorrect')
            self.state = self.State.START
            return False
