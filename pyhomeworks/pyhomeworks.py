"""
Homeworks.

A partial implementation of an interface to series-4 and series-8 Lutron
Homeworks systems.

The Series4/8 is connected to an RS232 port to an Ethernet adaptor (NPort).

Michael Dubno - 2018 - New York
"""
import logging
import select
import socket
import time
from threading import Thread

_LOGGER = logging.getLogger(__name__)


def _p_address(arg):    return arg
def _p_button(arg):     return int(arg)
def _p_enabled(arg):    return arg == 'enabled'
def _p_level(arg):      return int(arg)
def _p_ledstate(arg):   return [int(num) for num in arg]

def _norm(x): return (x, _p_address, _p_button)


# Callback types
HW_BUTTON_DOUBLE_TAP = 'button_double_tap'
HW_BUTTON_HOLD = 'button_hold'
HW_BUTTON_PRESSED = 'button_pressed'
HW_BUTTON_RELEASED = 'button_released'
HW_KEYPAD_ENABLE_CHANGED = 'keypad_enable_changed'
HW_KEYPAD_LED_CHANGED = 'keypad_led_changed'
HW_LIGHT_CHANGED = 'light_changed'

ACTIONS = {
    "KBP":   _norm(HW_BUTTON_PRESSED),
    "KBR":   _norm(HW_BUTTON_RELEASED),
    "KBH":   _norm(HW_BUTTON_HOLD),
    "KBDT":  _norm(HW_BUTTON_DOUBLE_TAP),
    "DBP":   _norm(HW_BUTTON_PRESSED),
    "DBR":   _norm(HW_BUTTON_RELEASED),
    "DBH":   _norm(HW_BUTTON_HOLD),
    "DBDT":  _norm(HW_BUTTON_DOUBLE_TAP),
    "SVBP":  _norm(HW_BUTTON_PRESSED),
    "SVBR":  _norm(HW_BUTTON_RELEASED),
    "SVBH":  _norm(HW_BUTTON_HOLD),
    "SVBDT": _norm(HW_BUTTON_DOUBLE_TAP),
    "KLS":   (HW_KEYPAD_LED_CHANGED, _p_address, _p_ledstate),
    "DL":    (HW_LIGHT_CHANGED, _p_address, _p_level),
    "KES":   (HW_KEYPAD_ENABLE_CHANGED, _p_address, _p_enabled),
}


class Homeworks(Thread):
    """Interface with a Lutron Homeworks 4/8 Series system."""
    _socket: socket.socket

    LOGIN_REQUEST = b'LOGIN: '
    POLLING_FREQ = 1.
    LOGIN_PROMPT_WAIT_TIME = 0.2

    def __init__(self, host, port, callback, autostart=True, login=None):
        """Connect to controller using host, port.
        :param login:
        """
        Thread.__init__(self)
        self._host = host
        self._port = port
        self._login = login
        self._callback = callback
        self._socket = None
        self._command_separator = b'\r\n'

        self._running = False

        if autostart:
            self.start()

    def _connect(self):
        try:
            self._socket = socket.create_connection((self._host, self._port))
            _LOGGER.info(f"Connected to '{self._host}:{self._port}'")
        except (BlockingIOError, ConnectionError, TimeoutError) as error:
            raise ConnectionError(f"Couldn't connect to '{self._host}:{self._port}': {error}")

    def _send(self, command):
        _LOGGER.debug("send: %s", command)
        try:
            self._socket.send(command.encode('utf8') + self._command_separator)
            return True
        except (ConnectionError, AttributeError):
            self._socket = None
            return False

    def fade_dim(self, intensity, fade_time, delay_time, addr):
        """Change the brightness of a light."""
        self._send('FADEDIM, %d, %d, %d, %s' %
                   (intensity, fade_time, delay_time, addr))

    def request_dimmer_level(self, addr):
        """Request the controller to return brightness."""
        self._send('RDL, %s' % addr)

    def run(self):
        """Read and dispatch messages from the controller."""
        self._running = True
        buffer = b''
        start_time = time.time()
        subscribed = False
        logged_in = self._login is None
        while self._running:
            if self._socket is None:
                start_time = time.time()
                self._connect()
            else:
                try:
                    if logged_in and not subscribed and time.time() - start_time > self.LOGIN_PROMPT_WAIT_TIME:
                        self._subscribe()
                        subscribed = True
                    readable, _, _ = select.select([self._socket], [], [], self.POLLING_FREQ)
                    if len(readable) != 0:
                        buffer += self._socket.recv(1024)
                        if buffer.startswith(self.LOGIN_REQUEST):
                            self._handle_login_request()
                            logged_in = True
                            buffer = buffer[len(self.LOGIN_REQUEST):]
                            continue
                        while True:
                            (command, separator, remainder) = buffer.partition(self._command_separator)
                            if separator != self._command_separator:
                                break
                            buffer = remainder
                            self._processReceivedData(command.decode('utf-8'))
                except (ConnectionError, AttributeError):
                    _LOGGER.warning("Lost connection.")
                    self._socket = None
                    subscribed = False
                    logged_in = self._login is None
                    buffer = b''
                    if self._running:
                        time.sleep(self.POLLING_FREQ)
                except UnicodeDecodeError:
                    pass

    def _processReceivedData(self, data: str):
        _LOGGER.debug("Raw: %s", data)
        try:
            raw_args = data.split(', ')
            action = ACTIONS.get(raw_args[0], None)
            if action and len(raw_args) == len(action):
                args = [parser(arg) for parser, arg in
                        zip(action[1:], raw_args[1:])]
                self._callback(action[0], args)
            else:
                _LOGGER.warning("Not handling: %s", raw_args)
        except ValueError:
            _LOGGER.warning("Weird data: %s", data)

    def close(self):
        """Close the connection to the controller."""
        self._running = False
        if self._socket:
            # time.sleep(POLLING_FREQ)
            self._socket.close()
            self._socket = None

    def _handle_login_request(self):
        self._send(self._login)

    def _subscribe(self):
        # Setup interface and subscribe to events
        self._send('PROMPTOFF')  # No prompt is needed
        self._send('KBMON')  # Monitor keypad events
        self._send('GSMON')  # Monitor GRAFIKEYE scenes
        self._send('DLMON')  # Monitor dimmer levels
        self._send('KLMON')  # Monitor keypad LED states
