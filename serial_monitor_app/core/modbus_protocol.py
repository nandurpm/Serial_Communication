#!/usr/bin/env python3
"""
Modbus Protocol Implementation
Supports Modbus RTU and Modbus TCP protocols with CRC validation.
"""

import struct
import logging
from typing import List, Optional, Tuple
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ModbusFunction(Enum):
    """Modbus function codes."""
    READ_COILS = 0x01
    READ_DISCRETE_INPUTS = 0x02
    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04
    WRITE_SINGLE_COIL = 0x05
    WRITE_SINGLE_REGISTER = 0x06
    WRITE_MULTIPLE_COILS = 0x0F
    WRITE_MULTIPLE_REGISTERS = 0x10


class ModbusRTU:
    """Modbus RTU Protocol Handler."""

    def __init__(self, serial_handler, slave_id: int = 1):
        """
        Initialize Modbus RTU.

        Args:
            serial_handler: SerialPortHandler instance
            slave_id: Slave device ID (1-247)
        """
        self.serial_handler = serial_handler
        self.slave_id = slave_id
        self.timeout = 1.0
        self.transaction_id = 0

    def read_holding_registers(
        self,
        start_address: int,
        quantity: int
    ) -> Optional[List[int]]:
        """Read holding registers (function code 03)."""
        if quantity < 1 or quantity > 125:
            logger.error(f"Invalid quantity: {quantity}")
            return None

        request = self._build_request(
            ModbusFunction.READ_HOLDING_REGISTERS,
            start_address,
            quantity
        )

        response = self._send_request(request)
        if response:
            return self._parse_registers(response)
        return None

    def read_input_registers(
        self,
        start_address: int,
        quantity: int
    ) -> Optional[List[int]]:
        """Read input registers (function code 04)."""
        if quantity < 1 or quantity > 125:
            logger.error(f"Invalid quantity: {quantity}")
            return None

        request = self._build_request(
            ModbusFunction.READ_INPUT_REGISTERS,
            start_address,
            quantity
        )

        response = self._send_request(request)
        if response:
            return self._parse_registers(response)
        return None

    def read_coils(
        self,
        start_address: int,
        quantity: int
    ) -> Optional[List[bool]]:
        """Read coils (function code 01)."""
        if quantity < 1 or quantity > 2000:
            logger.error(f"Invalid quantity: {quantity}")
            return None

        request = self._build_request(
            ModbusFunction.READ_COILS,
            start_address,
            quantity
        )

        response = self._send_request(request)
        if response:
            return self._parse_coils(response)
        return None

    def write_single_register(
        self,
        address: int,
        value: int
    ) -> bool:
        """Write single register (function code 06)."""
        request = bytearray([self.slave_id, ModbusFunction.WRITE_SINGLE_REGISTER.value])
        request.extend(struct.pack('>HH', address, value))
        crc = self._calculate_crc(request)
        request.extend(struct.pack('<H', crc))

        response = self._send_request(bytes(request))
        return response is not None

    def write_multiple_registers(
        self,
        start_address: int,
        values: List[int]
    ) -> bool:
        """Write multiple registers (function code 16)."""
        if len(values) < 1 or len(values) > 123:
            logger.error(f"Invalid number of values: {len(values)}")
            return False

        request = bytearray([self.slave_id, ModbusFunction.WRITE_MULTIPLE_REGISTERS.value])
        request.extend(struct.pack('>H', start_address))
        request.extend(struct.pack('>H', len(values)))
        request.append(len(values) * 2)

        for value in values:
            request.extend(struct.pack('>H', value))

        crc = self._calculate_crc(request)
        request.extend(struct.pack('<H', crc))

        response = self._send_request(bytes(request))
        return response is not None

    def _build_request(
        self,
        function: ModbusFunction,
        start_address: int,
        quantity: int
    ) -> bytes:
        """Build Modbus request."""
        request = bytearray([self.slave_id, function.value])
        request.extend(struct.pack('>HH', start_address, quantity))
        crc = self._calculate_crc(request)
        request.extend(struct.pack('<H', crc))
        return bytes(request)

    def _send_request(self, request: bytes) -> Optional[bytes]:
        """Send request and receive response."""
        try:
            self.serial_handler.write(request)
            response = self.serial_handler.read(timeout=self.timeout)
            if response and self._validate_response(response):
                return response
        except Exception as e:
            logger.error(f"Request failed: {e}")
        return None

    def _validate_response(self, response: bytes) -> bool:
        """Validate Modbus response."""
        if len(response) < 3:
            return False

        if response[0] != self.slave_id:
            logger.error(f"Invalid slave ID: {response[0]}")
            return False

        if response[1] & 0x80:  # Error response
            logger.error(f"Modbus error code: {response[2]}")
            return False

        crc_received = struct.unpack('<H', response[-2:])[0]
        crc_calculated = self._calculate_crc(response[:-2])
        if crc_received != crc_calculated:
            logger.error(f"CRC mismatch: {crc_received} != {crc_calculated}")
            return False

        return True

    def _parse_registers(self, response: bytes) -> Optional[List[int]]:
        """Parse register values from response."""
        try:
            byte_count = response[2]
            registers = []
            for i in range(0, byte_count, 2):
                value = struct.unpack('>H', response[3 + i:5 + i])[0]
                registers.append(value)
            return registers
        except Exception as e:
            logger.error(f"Register parsing failed: {e}")
            return None

    def _parse_coils(self, response: bytes) -> Optional[List[bool]]:
        """Parse coil values from response."""
        try:
            byte_count = response[2]
            coils = []
            for i in range(byte_count):
                byte_val = response[3 + i]
                for bit in range(8):
                    coils.append(bool((byte_val >> bit) & 1))
            return coils
        except Exception as e:
            logger.error(f"Coil parsing failed: {e}")
            return None

    @staticmethod
    def _calculate_crc(data: bytes) -> int:
        """Calculate CRC16-MODBUS."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
