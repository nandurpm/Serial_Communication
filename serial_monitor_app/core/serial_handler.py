#!/usr/bin/env python3
"""
Serial Port Handler Module
Manages serial port operations with error handling and connection management.
"""

import serial
import threading
import queue
import logging
from typing import Optional, Callable, List
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class SerialPortHandler:
    """Handles serial port communication with thread-safe operations."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        parity: str = 'N',
        stopbits: int = 1,
        timeout: float = 1.0,
        rx_callback: Optional[Callable] = None
    ):
        """
        Initialize serial port handler.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0')
            baudrate: Communication speed (default: 9600)
            parity: Parity bit (N/E/O)
            stopbits: Stop bits (1/2)
            timeout: Read timeout in seconds
            rx_callback: Callback function for received data
        """
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.rx_callback = rx_callback

        self.serial = None
        self.is_connected = False
        self.rx_queue = queue.Queue()
        self.tx_queue = queue.Queue()
        self.rx_thread = None
        self.tx_thread = None
        self.running = False

        # Statistics
        self.stats = {
            'bytes_sent': 0,
            'bytes_received': 0,
            'packets_sent': 0,
            'packets_received': 0,
            'errors': 0,
            'last_rx_time': None,
            'last_tx_time': None
        }

    def connect(self) -> bool:
        """Establish serial connection."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout
            )
            self.is_connected = True
            self.running = True

            # Start receiver thread
            self.rx_thread = threading.Thread(target=self._receiver_thread, daemon=True)
            self.rx_thread.start()

            # Start transmitter thread
            self.tx_thread = threading.Thread(target=self._transmitter_thread, daemon=True)
            self.tx_thread.start()

            logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Close serial connection."""
        self.running = False
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.is_connected = False
        logger.info(f"Disconnected from {self.port}")

    def write(self, data: bytes) -> bool:
        """Queue data for transmission."""
        if not self.is_connected:
            logger.warning("Cannot write: not connected")
            return False
        try:
            self.tx_queue.put(data, timeout=1)
            return True
        except queue.Full:
            logger.error("TX queue full")
            return False

    def read(self, size: int = 1024, timeout: float = None) -> Optional[bytes]:
        """Read data from RX queue."""
        try:
            return self.rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _receiver_thread(self):
        """Background thread for receiving data."""
        while self.running:
            try:
                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    if data:
                        self.rx_queue.put(data)
                        self.stats['bytes_received'] += len(data)
                        self.stats['packets_received'] += 1
                        self.stats['last_rx_time'] = datetime.now()

                        if self.rx_callback:
                            self.rx_callback(data)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"RX thread error: {e}")
                self.stats['errors'] += 1
                time.sleep(0.1)

    def _transmitter_thread(self):
        """Background thread for transmitting data."""
        while self.running:
            try:
                data = self.tx_queue.get(timeout=0.1)
                self.serial.write(data)
                self.stats['bytes_sent'] += len(data)
                self.stats['packets_sent'] += 1
                self.stats['last_tx_time'] = datetime.now()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TX thread error: {e}")
                self.stats['errors'] += 1

    def get_stats(self) -> dict:
        """Get communication statistics."""
        return self.stats.copy()

    def clear_buffers(self):
        """Clear RX and TX buffers."""
        self.rx_queue = queue.Queue()
        self.tx_queue = queue.Queue()
        if self.serial:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()


class SerialPortFinder:
    """Find available serial ports on Linux."""

    @staticmethod
    def list_ports() -> List[dict]:
        """List all available serial ports."""
        ports = []
        for i in range(10):
            port = f"/dev/ttyUSB{i}"
            try:
                s = serial.Serial(port, timeout=0.1)
                ports.append({
                    'port': port,
                    'description': f"USB Serial Device {i}"
                })
                s.close()
            except:
                pass

        for i in range(10):
            port = f"/dev/ttyACM{i}"
            try:
                s = serial.Serial(port, timeout=0.1)
                ports.append({
                    'port': port,
                    'description': f"USB ACM Device {i}"
                })
                s.close()
            except:
                pass
        return ports
