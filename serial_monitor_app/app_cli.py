#!/usr/bin/env python3
"""
Command-Line Interface Application
CLI for serial communication monitoring and control.
"""

import argparse
import sys
import time
import json
from typing import List, Optional

from core.serial_handler import SerialPortHandler, SerialPortFinder
from core.modbus_protocol import ModbusRTU
from core.data_mapper import DataMapper, AddressMap, DataType
from core.storage import FileStorage, DatabaseStorage
from core.utils import format_hex, format_ascii, setup_logging

setup_logging()


class SerialMonitorCLI:
    """Command-line interface for serial monitoring."""

    def __init__(self):
        self.serial_handler = None
        self.modbus = None
        self.mapper = DataMapper()
        self.storage = FileStorage()
        self.db_storage = DatabaseStorage()

    def list_ports(self):
        """List available serial ports."""
        finder = SerialPortFinder()
        ports = finder.list_ports()
        print("\nAvailable Serial Ports:")
        for port in ports:
            print(f"  {port['port']}: {port['description']}")
        if not ports:
            print("  No ports found")

    def connect(self, port: str, baudrate: int = 9600):
        """Connect to serial port."""
        try:
            self.serial_handler = SerialPortHandler(port, baudrate)
            if self.serial_handler.connect():
                self.modbus = ModbusRTU(self.serial_handler)
                print(f"✓ Connected to {port} at {baudrate} baud")
                return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
        return False

    def disconnect(self):
        """Disconnect from serial port."""
        if self.serial_handler:
            self.serial_handler.disconnect()
            print("✓ Disconnected")

    def read_holding_registers(self, start: int, count: int):
        """Read holding registers."""
        if not self.modbus:
            print("✗ Not connected")
            return

        data = self.modbus.read_holding_registers(start, count)
        if data:
            print(f"\nRegisters {start}-{start + count - 1}:")
            print(f"{'Index':<10} {'Address':<12} {'Hex':<8} {'Dec':<10} {'Signed'}")
            print("-" * 50)
            for i, value in enumerate(data):
                address = start + i
                signed = value if value < 32768 else value - 65536
                print(f"{i:<10} {address:<12} {value:04X}     {value:<10} {signed}")
        else:
            print("✗ Failed to read registers")

    def write_register(self, address: int, value: int):
        """Write single register."""
        if not self.modbus:
            print("✗ Not connected")
            return

        if self.modbus.write_single_register(address, value):
            print(f"✓ Written {value} to register {address}")
        else:
            print(f"✗ Failed to write to register {address}")

    def scan_device(self, start: int = 0, end: int = 100, interval: float = 1.0):
        """Continuous device scan."""
        if not self.modbus:
            print("✗ Not connected")
            return

        print(f"Starting scan from {start} to {end}")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                data = self.modbus.read_holding_registers(start, end - start + 1)
                if data:
                    timestamp = time.strftime("%H:%M:%S")
                    print(f"[{timestamp}]", end=" ")
                    print(" ".join(f"{v:04X}" for v in data[:10]), end="")
                    if len(data) > 10:
                        print(f" ... ({len(data)} total)", end="")
                    print()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n✓ Scan stopped")

    def export_data(self, format: str = "json"):
        """Export data to file."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"export_{timestamp}.{format}"

        if format == "json":
            self.storage.save_json(filename, {})
        elif format == "csv":
            self.storage.save_csv(filename, [])

        print(f"✓ Data exported to {filename}")

    def show_stats(self):
        """Show communication statistics."""
        if not self.serial_handler:
            print("✗ Not connected")
            return

        stats = self.serial_handler.get_stats()
        print("\nCommunication Statistics:")
        print(f"  Bytes Sent:      {stats['bytes_sent']}")
        print(f"  Bytes Received:  {stats['bytes_received']}")
        print(f"  Packets Sent:    {stats['packets_sent']}")
        print(f"  Packets Received: {stats['packets_received']}")
        print(f"  Errors:          {stats['errors']}")
        print(f"  Last RX:         {stats['last_rx_time']}")
        print(f"  Last TX:         {stats['last_tx_time']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Serial Communication Monitor - Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list-ports
  %(prog)s -p /dev/ttyUSB0 -b 9600 read-registers 0 10
  %(prog)s -p /dev/ttyUSB0 -b 9600 scan -s 0 -e 50
        """
    )

    parser.add_argument(
        "-p", "--port",
        help="Serial port (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument(
        "-b", "--baudrate",
        type=int,
        default=9600,
        help="Baudrate (default: 9600)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # list-ports command
    subparsers.add_parser("list-ports", help="List available serial ports")

    # read-registers command
    read_parser = subparsers.add_parser("read-registers", help="Read holding registers")
    read_parser.add_argument("start", type=int, help="Start address")
    read_parser.add_argument("count", type=int, help="Number of registers")

    # write-register command
    write_parser = subparsers.add_parser("write-register", help="Write single register")
    write_parser.add_argument("address", type=int, help="Register address")
    write_parser.add_argument("value", type=int, help="Value to write")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Continuous device scan")
    scan_parser.add_argument("-s", "--start", type=int, default=0, help="Start address")
    scan_parser.add_argument("-e", "--end", type=int, default=100, help="End address")
    scan_parser.add_argument("-i", "--interval", type=float, default=1.0, help="Scan interval (seconds)")

    # export command
    export_parser = subparsers.add_parser("export", help="Export data")
    export_parser.add_argument("-f", "--format", choices=["json", "csv"], default="json")

    # stats command
    subparsers.add_parser("stats", help="Show communication statistics")

    args = parser.parse_args()

    cli = SerialMonitorCLI()

    # Execute commands
    if args.command == "list-ports":
        cli.list_ports()
    elif args.command == "read-registers":
        if cli.connect(args.port, args.baudrate):
            cli.read_holding_registers(args.start, args.count)
            cli.disconnect()
    elif args.command == "write-register":
        if cli.connect(args.port, args.baudrate):
            cli.write_register(args.address, args.value)
            cli.disconnect()
    elif args.command == "scan":
        if cli.connect(args.port, args.baudrate):
            cli.scan_device(args.start, args.end, args.interval)
            cli.disconnect()
    elif args.command == "export":
        cli.export_data(args.format)
    elif args.command == "stats":
        if cli.connect(args.port, args.baudrate):
            cli.show_stats()
            cli.disconnect()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
