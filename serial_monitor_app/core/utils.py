#!/usr/bin/env python3
"""
Utility Functions
Common utilities for the serial communication app.
"""

import logging
from typing import List
from datetime import datetime
import struct


def setup_logging(log_file: str = "app.log", level=logging.DEBUG):
    """Setup logging configuration."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )


def format_hex(data: bytes, separator: str = " ") -> str:
    """Format bytes as hex string."""
    return separator.join(f"{byte:02X}" for byte in data)


def parse_hex(hex_string: str) -> bytes:
    """Parse hex string to bytes."""
    hex_string = hex_string.replace(" ", "").replace(":", "")
    return bytes.fromhex(hex_string)


def format_ascii(data: bytes) -> str:
    """Format bytes as ASCII string (printable only)."""
    return ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)


def bytes_to_int16(data: bytes, offset: int = 0, signed: bool = True) -> int:
    """Convert bytes to 16-bit integer."""
    value = struct.unpack('>H' if not signed else '>h', data[offset:offset+2])[0]
    return value


def bytes_to_int32(data: bytes, offset: int = 0, signed: bool = True) -> int:
    """Convert bytes to 32-bit integer."""
    value = struct.unpack('>I' if not signed else '>i', data[offset:offset+4])[0]
    return value


def bytes_to_float32(data: bytes, offset: int = 0) -> float:
    """Convert bytes to 32-bit float."""
    return struct.unpack('>f', data[offset:offset+4])[0]


def int16_to_bytes(value: int) -> bytes:
    """Convert 16-bit integer to bytes."""
    return struct.pack('>h', value)


def int32_to_bytes(value: int) -> bytes:
    """Convert 32-bit integer to bytes."""
    return struct.pack('>i', value)


def float32_to_bytes(value: float) -> bytes:
    """Convert 32-bit float to bytes."""
    return struct.pack('>f', value)


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"
