#!/usr/bin/env python3
"""Thread-safe serial port discovery and communication helpers."""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

import serial
from serial.tools import list_ports

logger = logging.getLogger(__name__)


class SerialPortHandler:
    """Handle one serial connection with background receive buffering."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 1.0,
        rx_callback: Optional[Callable[[bytes], None]] = None,
    ) -> None:
        if not port:
            raise ValueError("A serial port is required")
        if int(baudrate) <= 0:
            raise ValueError("Baudrate must be greater than zero")

        self.port = port
        self.baudrate = int(baudrate)
        self.parity = parity.upper()
        self.stopbits = stopbits
        self.timeout = float(timeout)
        self.rx_callback = rx_callback

        self.serial: Optional[serial.Serial] = None
        self.is_connected = False
        self.running = False
        self.rx_queue: queue.Queue[bytes] = queue.Queue(maxsize=1000)
        self.rx_thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self.stats = {
            "bytes_sent": 0,
            "bytes_received": 0,
            "packets_sent": 0,
            "packets_received": 0,
            "errors": 0,
            "last_rx_time": None,
            "last_tx_time": None,
        }

    def connect(self) -> bool:
        """Open the configured port and start the receiver thread."""
        with self._state_lock:
            if self.is_connected and self.serial and self.serial.is_open:
                return True
            try:
                self.serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=0.05,
                    write_timeout=max(self.timeout, 0.1),
                )
                self.serial.reset_input_buffer()
                self.serial.reset_output_buffer()
                self.running = True
                self.is_connected = True
                self.rx_thread = threading.Thread(
                    target=self._receiver_thread,
                    name=f"serial-rx-{self.port}",
                    daemon=True,
                )
                self.rx_thread.start()
                logger.info("Connected to %s at %s baud", self.port, self.baudrate)
                return True
            except (serial.SerialException, ValueError, OSError) as exc:
                logger.error("Failed to connect to %s: %s", self.port, exc)
                self.serial = None
                self.running = False
                self.is_connected = False
                return False

    def disconnect(self) -> None:
        """Stop background work and close the serial port cleanly."""
        with self._state_lock:
            self.running = False
            serial_obj = self.serial

        if self.rx_thread and self.rx_thread.is_alive():
            self.rx_thread.join(timeout=1.0)

        with self._state_lock:
            if serial_obj and serial_obj.is_open:
                try:
                    serial_obj.close()
                except serial.SerialException as exc:
                    logger.warning("Error while closing %s: %s", self.port, exc)
            self.serial = None
            self.is_connected = False
            self.rx_thread = None
        logger.info("Disconnected from %s", self.port)

    def write(self, data: bytes) -> bool:
        """Write bytes synchronously so callers can safely wait for a reply."""
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise ValueError("data must be non-empty bytes")
        if not self.is_connected or not self.serial or not self.serial.is_open:
            logger.warning("Cannot write: not connected")
            return False

        try:
            with self._write_lock:
                written = self.serial.write(bytes(data))
                self.serial.flush()
            if written != len(data):
                logger.error("Partial serial write: %s of %s bytes", written, len(data))
                self.stats["errors"] += 1
                return False
            self.stats["bytes_sent"] += written
            self.stats["packets_sent"] += 1
            self.stats["last_tx_time"] = datetime.now()
            return True
        except (serial.SerialException, OSError) as exc:
            logger.error("Serial write failed: %s", exc)
            self.stats["errors"] += 1
            return False

    def read(self, size: int = 1024, timeout: Optional[float] = None) -> Optional[bytes]:
        """Return the next received chunk from the background queue."""
        del size
        try:
            return self.rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def discard_input(self) -> None:
        """Discard queued and operating-system buffered receive data."""
        while True:
            try:
                self.rx_queue.get_nowait()
            except queue.Empty:
                break
        if self.serial and self.serial.is_open:
            try:
                self.serial.reset_input_buffer()
            except serial.SerialException as exc:
                logger.warning("Unable to reset input buffer: %s", exc)

    def clear_buffers(self) -> None:
        """Clear receive and transmit buffers without replacing live queues."""
        self.discard_input()
        if self.serial and self.serial.is_open:
            try:
                self.serial.reset_output_buffer()
            except serial.SerialException as exc:
                logger.warning("Unable to reset output buffer: %s", exc)

    def _receiver_thread(self) -> None:
        """Continuously collect available bytes without blocking shutdown."""
        while self.running:
            serial_obj = self.serial
            if not serial_obj or not serial_obj.is_open:
                break
            try:
                waiting = serial_obj.in_waiting
                data = serial_obj.read(waiting or 1)
                if not data:
                    continue
                try:
                    self.rx_queue.put(data, timeout=0.1)
                except queue.Full:
                    self.stats["errors"] += 1
                    logger.error("RX queue full; dropping %s bytes", len(data))
                    continue

                self.stats["bytes_received"] += len(data)
                self.stats["packets_received"] += 1
                self.stats["last_rx_time"] = datetime.now()
                if self.rx_callback:
                    try:
                        self.rx_callback(data)
                    except Exception:
                        logger.exception("Receive callback failed")
            except (serial.SerialException, OSError) as exc:
                if self.running:
                    logger.error("RX thread error: %s", exc)
                    self.stats["errors"] += 1
                    time.sleep(0.05)

    def get_stats(self) -> dict:
        """Return a snapshot of communication counters."""
        return self.stats.copy()


class SerialPortFinder:
    """Discover serial ports without opening or locking them."""

    @staticmethod
    def list_ports() -> List[dict]:
        ports = []
        for port in sorted(list_ports.comports(), key=lambda item: item.device):
            ports.append(
                {
                    "port": port.device,
                    "description": port.description or "Serial device",
                    "manufacturer": port.manufacturer or "",
                    "vid": port.vid,
                    "pid": port.pid,
                    "serial_number": port.serial_number or "",
                }
            )
        return ports
