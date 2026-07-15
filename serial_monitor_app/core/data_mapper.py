#!/usr/bin/env python3
"""
Data Mapper Module
Maps RX values to registers, addresses, and labels with scaling and conversions.
"""

import struct
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class DataType(Enum):
    """Supported data types."""
    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    BOOL = "bool"
    STRING = "string"
    HEX = "hex"


@dataclass
class AddressMap:
    """Address mapping configuration."""
    device_id: str
    address: int
    label: str
    data_type: DataType
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    description: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    alarm_threshold: Optional[float] = None
    regex_pattern: Optional[str] = None
    _cache: Dict[str, Any] = field(default_factory=dict)
    _history: List[Dict[str, Any]] = field(default_factory=list)
    _max_history: int = 100


class DataMapper:
    """Maps raw serial data to device addresses and formatted values."""

    def __init__(self):
        self.maps: Dict[str, AddressMap] = {}
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.callbacks: Dict[str, List[callable]] = {}

    def add_mapping(self, mapping: AddressMap):
        """Add address mapping."""
        key = f"{mapping.device_id}:{mapping.address}"
        self.maps[key] = mapping
        if mapping.device_id not in self.callbacks:
            self.callbacks[mapping.device_id] = []
        logger.info(f"Added mapping: {mapping.label}")

    def add_device(self, device_id: str, config: Dict[str, Any]):
        """Register device configuration."""
        self.devices[device_id] = config
        logger.info(f"Added device: {device_id}")

    def map_value(
        self,
        device_id: str,
        address: int,
        raw_value: int
    ) -> Optional[Dict[str, Any]]:
        """
        Map raw value to formatted data.

        Args:
            device_id: Device identifier
            address: Register address
            raw_value: Raw register value

        Returns:
            Mapped data with label, scaled value, and unit
        """
        key = f"{device_id}:{address}"
        if key not in self.maps:
            return None

        mapping = self.maps[key]
        scaled_value = self._scale_value(raw_value, mapping)

        result = {
            'device_id': device_id,
            'address': address,
            'label': mapping.label,
            'raw_value': raw_value,
            'scaled_value': scaled_value,
            'unit': mapping.unit,
            'data_type': mapping.data_type.value,
            'timestamp': datetime.now().isoformat(),
            'in_alarm': False
        }

        # Check alarm threshold
        if mapping.alarm_threshold and scaled_value > mapping.alarm_threshold:
            result['in_alarm'] = True
            logger.warning(f"ALARM: {mapping.label} = {scaled_value} {mapping.unit}")

        # Validate range
        if mapping.min_value and scaled_value < mapping.min_value:
            result['warning'] = f"Below minimum: {mapping.min_value}"
        if mapping.max_value and scaled_value > mapping.max_value:
            result['warning'] = f"Above maximum: {mapping.max_value}"

        # Update cache and history
        mapping._cache = result
        mapping._history.append(result)
        if len(mapping._history) > mapping._max_history:
            mapping._history.pop(0)

        # Trigger callbacks
        self._trigger_callbacks(device_id, mapping, result)

        return result

    def map_register_block(
        self,
        device_id: str,
        start_address: int,
        values: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Map multiple register values.

        Args:
            device_id: Device identifier
            start_address: Starting address
            values: List of register values

        Returns:
            List of mapped data
        """
        results = []
        for i, value in enumerate(values):
            address = start_address + i
            mapped = self.map_value(device_id, address, value)
            if mapped:
                results.append(mapped)
        return results

    def _scale_value(self, raw_value: int, mapping: AddressMap) -> float:
        """
        Apply scaling and offset to raw value.

        Args:
            raw_value: Raw register value
            mapping: Address mapping configuration

        Returns:
            Scaled value
        """
        # Handle signed integers
        if mapping.data_type in [DataType.INT16, DataType.INT32]:
            if mapping.data_type == DataType.INT16:
                if raw_value > 32767:
                    raw_value = raw_value - 65536
            elif mapping.data_type == DataType.INT32:
                if raw_value > 2147483647:
                    raw_value = raw_value - 4294967296

        # Apply scaling and offset
        scaled = (raw_value * mapping.scale) + mapping.offset
        return round(scaled, 4)

    def get_value(self, device_id: str, address: int) -> Optional[Dict[str, Any]]:
        """Get cached value."""
        key = f"{device_id}:{address}"
        if key in self.maps:
            return self.maps[key]._cache
        return None

    def get_history(
        self,
        device_id: str,
        address: int,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """Get value history."""
        key = f"{device_id}:{address}"
        if key in self.maps:
            history = self.maps[key]._history
            return history[-limit:] if limit else history
        return []

    def register_callback(
        self,
        device_id: str,
        callback: callable
    ):
        """Register callback for device updates."""
        if device_id not in self.callbacks:
            self.callbacks[device_id] = []
        self.callbacks[device_id].append(callback)

    def _trigger_callbacks(
        self,
        device_id: str,
        mapping: AddressMap,
        result: Dict[str, Any]
    ):
        """Trigger registered callbacks."""
        if device_id in self.callbacks:
            for callback in self.callbacks[device_id]:
                try:
                    callback(mapping, result)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    def get_all_mappings(self, device_id: str = None) -> Dict[str, AddressMap]:
        """Get mappings, optionally filtered by device."""
        if device_id:
            return {k: v for k, v in self.maps.items() if v.device_id == device_id}
        return self.maps

    def get_statistics(
        self,
        device_id: str,
        address: int
    ) -> Optional[Dict[str, float]]:
        """Calculate statistics for address history."""
        history = self.get_history(device_id, address)
        if not history:
            return None

        values = [h['scaled_value'] for h in history]
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'latest': values[-1] if values else None
        }
