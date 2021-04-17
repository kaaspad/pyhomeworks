import logging
import queue
from socket import socket
from time import sleep
from unittest.mock import Mock, call

import pytest

from pyhomeworks import Homeworks
from .device import HomeworksDevice

logging.basicConfig(level=logging.DEBUG)


class Buffer:
    def __init__(self):
        self._queue = queue.Queue()
        self._buffer = b''

    def recv(self, bytes_len):
        if len(self._buffer) < bytes_len:
            try:
                data = self._queue.get_nowait()
                if len(data):
                    self._buffer += data
            except queue.Empty:
                pass

        out = self._buffer[:bytes_len]
        self._buffer = self._buffer[len(out):]
        return out

    def put(self, data: bytes):
        self._queue.put_nowait(data)


@pytest.fixture
def hw_device(in_buffer, mocker):
    device = HomeworksDevice(on_send=in_buffer.put)
    mocker.spy(device, 'receive')
    mocker.spy(device, 'send')
    return device


@pytest.fixture
def in_buffer():
    return Buffer()


@pytest.fixture()
def lib(mocker, socket_mock):
    mocker.patch("socket.create_connection").return_value = socket_mock
    mocker.patch("select.select").return_value = ([1], 0, 0)

    return Homeworks('127.0.0.1', 4003, dummy_callback, autostart=False)


@pytest.fixture()
def lib_with_login(mocker, socket_mock):
    mocker.patch("socket.create_connection").return_value = socket_mock
    mocker.patch("select.select").return_value = ([1], 0, 0)

    return Homeworks('127.0.0.1', 4003, dummy_callback, login="user,password", autostart=False)


@pytest.fixture
def socket_mock(in_buffer, hw_device: HomeworksDevice):
    sm = Mock(spec_set=socket)
    sm.fileno.return_value = 0
    sm.recv.side_effect = in_buffer.recv
    sm.send.side_effect = hw_device.receive

    return sm


def dummy_callback(data):
    print(data)


def test_connect_without_login(hw_device, lib, socket_mock):
    try:
        hw_device.start()
        lib.start()

        sleep(0.2)
    except Exception:
        raise

    finally:
        lib.close()
        lib.join(1)
        hw_device.stop()
        hw_device.join(1)

    assert_subscribe(hw_device, socket_mock)


def assert_subscribe(hw_device, socket_mock):
    socket_mock.send.assert_any_call(b'PROMPTOFF\r\n')
    socket_mock.send.assert_any_call(b'KBMON\r\n')
    socket_mock.send.assert_any_call(b'GSMON\r\n')
    socket_mock.send.assert_any_call(b'DLMON\r\n')
    socket_mock.send.assert_any_call(b'KLMON\r\n')
    hw_device.send.assert_any_call(b'Keypad button monitoring enabled\r\n')
    hw_device.send.assert_any_call(b'GrafikEye scene monitoring enabled\r\n')
    hw_device.send.assert_any_call(b'Dimmer level monitoring enabled\r\n')
    hw_device.send.assert_any_call(b'Keypad led monitoring enabled\r\n')


def test_connect_with_login(hw_device, lib_with_login, socket_mock):
    hw_device.require_login = 'user,password'
    try:
        hw_device.start()
        lib_with_login.start()

        sleep(0.2)
    except Exception:
        raise

    finally:
        lib_with_login.close()
        lib_with_login.join(1)
        hw_device.stop()
        hw_device.join(1)

    assert_login(hw_device)
    assert_subscribe(hw_device, socket_mock)


def assert_login(hw_device):
    assert hw_device.send.call_args_list[0] == call(b'LOGIN: ')
    assert hw_device.receive.call_args_list[0] == call(b'user,password\r\n')