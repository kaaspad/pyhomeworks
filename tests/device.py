import queue
from threading import Thread
import logging

logger = logging.getLogger('mock_homeworks_device')


class HomeworksDevice(Thread):
    def __init__(self, on_send=lambda x: print(x), command_separator=b'\r\n'):
        Thread.__init__(self)
        self._receive_queue = queue.SimpleQueue()
        self._receive_buffer = b''

        self._command_separator = command_separator
        self._on_send = on_send
        self.require_login = False

    def send(self, data: bytes) -> None:
        logger.debug(f"send: {data}")
        self._on_send(data)

    def receive(self, data:bytes) -> None:
        logger.debug(f"receive: {data}")
        self._receive_queue.put_nowait(data)

    def run(self) -> None:
        sent_login_request = False
        while True:
            if self.require_login and not sent_login_request :
                self.send(b'LOGIN: ')
                sent_login_request = True
            buf = self._receive_queue.get()
            if buf is None:
                return
            self._receive_buffer += buf
            self.check_buffer_for_commands()

    def stop(self):
        self._receive_queue.put_nowait(None)

    def check_buffer_for_commands(self):
        while True:
            (command, separator, remainder) = self._receive_buffer.partition(self._command_separator)
            if separator != self._command_separator:
                return
            self._receive_buffer = remainder
            self.on_command(command)

    def on_command(self, command):
        if command.rstrip() == b'KBMON':
            self.send(b'Keypad button monitoring enabled'+self._command_separator)
        elif command.rstrip() == b'GSMON':
            self.send(b'GrafikEye scene monitoring enabled'+self._command_separator)
        elif command.rstrip() == b'DLMON':
            self.send(b'Dimmer level monitoring enabled'+self._command_separator)
        elif command.rstrip() == b'KLMON':
            self.send(b'Keypad led monitoring enabled'+self._command_separator)