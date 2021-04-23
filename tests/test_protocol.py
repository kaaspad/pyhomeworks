import asyncio
from asyncio import InvalidStateError

import pytest

from pyhomeworks.exceptions import HomeworksNoCredentialsProvided, InvalidCredentialsProvided, HomeworksConnectionLost
from pyhomeworks.protocol import HomeworksProtocol


@pytest.fixture
def transport(mocker):
    m = mocker.Mock()
    m.is_closing.return_value = False
    return m


@pytest.fixture
def protocol(transport) -> HomeworksProtocol:
    p = HomeworksProtocol()
    p.connection_made(transport)

    return p


@pytest.fixture
def protocol_with_credentials(transport) -> HomeworksProtocol:
    p = HomeworksProtocol(credentials="user,pass")
    p.connection_made(transport)

    return p


def test_creation(protocol):
    with pytest.raises(InvalidStateError):
        protocol.ready_future.result()


def test_ready_with_LNET_prompt(protocol):
    protocol.data_received(b'LNET> ')
    assert protocol.ready_future.result() is True


def test_ready_with_L232_prompt(protocol):
    protocol.data_received(b'L232> ')
    assert protocol.ready_future.result() is True


@pytest.mark.asyncio
async def test_ready_without_prompt_timeout(protocol):
    await asyncio.sleep(0.1)
    with pytest.raises(InvalidStateError):
        protocol.ready_future.result()

    await asyncio.sleep(0.2)
    assert protocol.ready_future.result() is True


def test_login_without_credentials(protocol):
    with pytest.raises(HomeworksNoCredentialsProvided):
        protocol.data_received(b'LOGIN: ')

    with pytest.raises(HomeworksNoCredentialsProvided):
        protocol.ready_future.result()


def test_login_with_credentials(protocol_with_credentials, transport):
    protocol_with_credentials.data_received(b'LOGIN: ')
    transport.write.assert_called_with(b'user,pass\r\n')

    with pytest.raises(InvalidStateError):
        protocol_with_credentials.ready_future.result()

    protocol_with_credentials.data_received(b'login successful\r\n')

    assert protocol_with_credentials.ready_future.result() is True


def test_login_with_wrong_credentials(protocol_with_credentials, transport):
    protocol_with_credentials.data_received(b'LOGIN: ')
    transport.write.assert_called_with(b'user,pass\r\n')
    with pytest.raises(InvalidCredentialsProvided):
        protocol_with_credentials.data_received(b'login incorrect\r\n')

    with pytest.raises(InvalidCredentialsProvided):
        protocol_with_credentials.ready_future.result()


def test_ready_with_an_event(protocol):
    protocol.data_received(b'DL, [01:01:00:03:02],   0\r\n')
    assert protocol.ready_future.result() is True

    assert protocol.read_queue.get_nowait() == 'DL, [01:01:00:03:02],   0'
    with pytest.raises(asyncio.QueueEmpty):
        protocol.read_queue.get_nowait()


def test_read_queue_extra_lines(protocol):
    protocol.data_received(b'\r\n\r\n\r\nDL, [01:01:00:03:02],   0\r\n\r\n\r\n')

    assert protocol.read_queue.get_nowait() == 'DL, [01:01:00:03:02],   0'
    with pytest.raises(asyncio.QueueEmpty):
        protocol.read_queue.get_nowait()


def test_receive_chunked(protocol):
    protocol.data_received(b'DL, [')
    protocol.data_received(b'01:01:00:03:02')
    protocol.data_received(b'],   0\r\n')

    assert protocol.read_queue.get_nowait() == 'DL, [01:01:00:03:02],   0'
    with pytest.raises(asyncio.QueueEmpty):
        protocol.read_queue.get_nowait()


def test_receive_multiple(protocol):
    protocol.data_received(b'DL, [01:01:00:03:01],   0\r\n')
    protocol.data_received(b'DL, [01:01:00:03:02],   1\r\n')

    assert protocol.read_queue.get_nowait() == 'DL, [01:01:00:03:01],   0'
    assert protocol.read_queue.get_nowait() == 'DL, [01:01:00:03:02],   1'
    with pytest.raises(asyncio.QueueEmpty):
        protocol.read_queue.get_nowait()


def test_connection_lost(protocol):
    with pytest.raises(InvalidStateError):
        protocol.connection_lost_future.result()
    protocol.connection_lost(IOError("Errors happen"))

    with pytest.raises(HomeworksConnectionLost):
        assert protocol.ready_future.result()

    with pytest.raises(HomeworksConnectionLost):
        protocol.connection_lost_future.result()


def test_connection_lost_without_exception(protocol):
    protocol.connection_lost(None)

    with pytest.raises(HomeworksConnectionLost):
        protocol.ready_future.result()

    with pytest.raises(HomeworksConnectionLost):
        protocol.connection_lost_future.result()