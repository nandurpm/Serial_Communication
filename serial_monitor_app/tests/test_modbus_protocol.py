"""Hardware-free tests for Modbus RTU frame handling."""

import struct

from core.modbus_protocol import ModbusRTU


class FakeSerialHandler:
    def __init__(self, response_chunks):
        self.is_connected = True
        self.response_chunks = list(response_chunks)
        self.written = []

    def discard_input(self):
        return None

    def write(self, data):
        self.written.append(data)
        return True

    def read(self, timeout=None):
        del timeout
        return self.response_chunks.pop(0) if self.response_chunks else None


def with_crc(payload: bytes) -> bytes:
    return payload + struct.pack("<H", ModbusRTU._calculate_crc(payload))


def test_crc_known_vector():
    request = bytes.fromhex("01 03 00 00 00 0A")
    assert ModbusRTU._calculate_crc(request) == 0xCDC5


def test_fragmented_register_response_is_reassembled():
    response = with_crc(bytes.fromhex("01 03 04 00 2A FF FE"))
    handler = FakeSerialHandler([response[:2], response[2:5], response[5:]])
    client = ModbusRTU(handler, slave_id=1, timeout=0.1)

    assert client.read_holding_registers(0, 2) == [42, 65534]
    assert handler.written[0].hex() == "010300000002c40b"


def test_bad_crc_is_rejected():
    response = bytearray(with_crc(bytes.fromhex("01 03 02 00 2A")))
    response[-1] ^= 0xFF
    client = ModbusRTU(FakeSerialHandler([bytes(response)]), slave_id=1, timeout=0.1)

    assert client.read_holding_registers(0, 1) is None


def test_invalid_register_quantity_is_rejected():
    client = ModbusRTU(FakeSerialHandler([]), slave_id=1)
    try:
        client.read_holding_registers(0, 126)
    except ValueError as exc:
        assert "between 1 and 125" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
