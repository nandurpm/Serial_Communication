#!/usr/bin/env python3
"""Minimal, validated Modbus RTU protocol implementation."""

from __future__ import annotations

import logging
import struct
import threading
import time
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class ModbusFunction(Enum):
    READ_COILS = 0x01
    READ_DISCRETE_INPUTS = 0x02
    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04
    WRITE_SINGLE_COIL = 0x05
    WRITE_SINGLE_REGISTER = 0x06
    WRITE_MULTIPLE_COILS = 0x0F
    WRITE_MULTIPLE_REGISTERS = 0x10


class ModbusRTU:
    """Perform one Modbus RTU transaction at a time over a serial handler."""

    def __init__(self, serial_handler, slave_id: int = 1, timeout: float = 1.0):
        if not 1 <= int(slave_id) <= 247:
            raise ValueError("slave_id must be between 1 and 247")
        self.serial_handler = serial_handler
        self.slave_id = int(slave_id)
        self.timeout = float(timeout)
        self._transaction_lock = threading.Lock()

    def read_holding_registers(self, start_address: int, quantity: int) -> Optional[List[int]]:
        return self._read_registers(ModbusFunction.READ_HOLDING_REGISTERS, start_address, quantity)

    def read_input_registers(self, start_address: int, quantity: int) -> Optional[List[int]]:
        return self._read_registers(ModbusFunction.READ_INPUT_REGISTERS, start_address, quantity)

    def _read_registers(self, function: ModbusFunction, start_address: int, quantity: int) -> Optional[List[int]]:
        self._validate_address(start_address)
        if not 1 <= int(quantity) <= 125:
            raise ValueError("Register quantity must be between 1 and 125")
        request = self._build_request(function, int(start_address), int(quantity))
        response = self._send_request(request, function)
        if response is None:
            return None
        values = self._parse_registers(response)
        if len(values) != int(quantity):
            logger.error("Expected %s registers but received %s", quantity, len(values))
            return None
        return values

    def read_coils(self, start_address: int, quantity: int) -> Optional[List[bool]]:
        self._validate_address(start_address)
        if not 1 <= int(quantity) <= 2000:
            raise ValueError("Coil quantity must be between 1 and 2000")
        request = self._build_request(ModbusFunction.READ_COILS, int(start_address), int(quantity))
        response = self._send_request(request, ModbusFunction.READ_COILS)
        if response is None:
            return None
        return self._parse_coils(response)[: int(quantity)]

    def write_single_register(self, address: int, value: int) -> bool:
        self._validate_address(address)
        self._validate_u16(value, "value")
        request = bytearray([self.slave_id, ModbusFunction.WRITE_SINGLE_REGISTER.value])
        request.extend(struct.pack(">HH", int(address), int(value)))
        request.extend(struct.pack("<H", self._calculate_crc(request)))
        response = self._send_request(bytes(request), ModbusFunction.WRITE_SINGLE_REGISTER)
        return response == bytes(request)

    def write_multiple_registers(self, start_address: int, values: List[int]) -> bool:
        self._validate_address(start_address)
        if not 1 <= len(values) <= 123:
            raise ValueError("values must contain between 1 and 123 registers")
        for value in values:
            self._validate_u16(value, "register value")
        if int(start_address) + len(values) - 1 > 0xFFFF:
            raise ValueError("Register range exceeds address 65535")

        request = bytearray([self.slave_id, ModbusFunction.WRITE_MULTIPLE_REGISTERS.value])
        request.extend(struct.pack(">HHB", int(start_address), len(values), len(values) * 2))
        for value in values:
            request.extend(struct.pack(">H", int(value)))
        request.extend(struct.pack("<H", self._calculate_crc(request)))

        response = self._send_request(bytes(request), ModbusFunction.WRITE_MULTIPLE_REGISTERS)
        if response is None or len(response) != 8:
            return False
        returned_start, returned_count = struct.unpack(">HH", response[2:6])
        return returned_start == int(start_address) and returned_count == len(values)

    def _build_request(self, function: ModbusFunction, start_address: int, quantity: int) -> bytes:
        request = bytearray([self.slave_id, function.value])
        request.extend(struct.pack(">HH", start_address, quantity))
        request.extend(struct.pack("<H", self._calculate_crc(request)))
        return bytes(request)

    def _send_request(self, request: bytes, function: ModbusFunction) -> Optional[bytes]:
        with self._transaction_lock:
            if not getattr(self.serial_handler, "is_connected", False):
                logger.error("Cannot perform Modbus transaction: serial port is disconnected")
                return None
            self.serial_handler.discard_input()
            if not self.serial_handler.write(request):
                return None
            response = self._read_frame(function)
            if response and self._validate_response(response, function):
                return response
            return None

    def _read_frame(self, function: ModbusFunction) -> Optional[bytes]:
        """Accumulate fragmented serial chunks until one complete RTU frame arrives."""
        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        expected_length: Optional[int] = None

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            chunk = self.serial_handler.read(timeout=min(remaining, 0.1))
            if chunk:
                buffer.extend(chunk)

            if len(buffer) >= 2 and buffer[1] & 0x80:
                expected_length = 5
            elif len(buffer) >= 3 and function in {
                ModbusFunction.READ_COILS,
                ModbusFunction.READ_DISCRETE_INPUTS,
                ModbusFunction.READ_HOLDING_REGISTERS,
                ModbusFunction.READ_INPUT_REGISTERS,
            }:
                expected_length = 5 + buffer[2]
            elif function in {
                ModbusFunction.WRITE_SINGLE_COIL,
                ModbusFunction.WRITE_SINGLE_REGISTER,
                ModbusFunction.WRITE_MULTIPLE_COILS,
                ModbusFunction.WRITE_MULTIPLE_REGISTERS,
            }:
                expected_length = 8

            if expected_length is not None and len(buffer) >= expected_length:
                return bytes(buffer[:expected_length])

        logger.error("Modbus response timed out after %.3f seconds", self.timeout)
        return None

    def _validate_response(self, response: bytes, expected_function: ModbusFunction) -> bool:
        if len(response) < 5:
            logger.error("Modbus frame is too short: %s bytes", len(response))
            return False
        if response[0] != self.slave_id:
            logger.error("Unexpected slave ID %s (expected %s)", response[0], self.slave_id)
            return False

        function_code = response[1]
        if function_code & 0x80:
            logger.error("Modbus exception %s for function 0x%02X", response[2], function_code & 0x7F)
            return False
        if function_code != expected_function.value:
            logger.error("Unexpected function 0x%02X (expected 0x%02X)", function_code, expected_function.value)
            return False

        received_crc = struct.unpack("<H", response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            logger.error("CRC mismatch: received %04X, calculated %04X", received_crc, calculated_crc)
            return False
        return True

    @staticmethod
    def _parse_registers(response: bytes) -> List[int]:
        byte_count = response[2]
        if byte_count % 2 or len(response) != byte_count + 5:
            raise ValueError("Invalid register response length")
        return [struct.unpack(">H", response[index:index + 2])[0] for index in range(3, 3 + byte_count, 2)]

    @staticmethod
    def _parse_coils(response: bytes) -> List[bool]:
        byte_count = response[2]
        if len(response) != byte_count + 5:
            raise ValueError("Invalid coil response length")
        coils: List[bool] = []
        for byte_value in response[3:3 + byte_count]:
            coils.extend(bool((byte_value >> bit) & 1) for bit in range(8))
        return coils

    @staticmethod
    def _validate_address(address: int) -> None:
        if not 0 <= int(address) <= 0xFFFF:
            raise ValueError("address must be between 0 and 65535")

    @staticmethod
    def _validate_u16(value: int, name: str) -> None:
        if not 0 <= int(value) <= 0xFFFF:
            raise ValueError(f"{name} must be between 0 and 65535")

    @staticmethod
    def _calculate_crc(data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc
