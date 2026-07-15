#!/usr/bin/env python3
"""Command-line interface for Modbus RTU serial monitoring."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.modbus_protocol import ModbusRTU
from core.serial_handler import SerialPortFinder, SerialPortHandler
from core.utils import setup_logging

setup_logging()


class SerialMonitorCLI:
    def __init__(self) -> None:
        self.serial_handler: Optional[SerialPortHandler] = None
        self.modbus: Optional[ModbusRTU] = None

    def list_ports(self) -> int:
        ports = SerialPortFinder.list_ports()
        if not ports:
            print("No serial ports found")
            return 1
        print(f"{'Port':<22} {'Description':<36} Manufacturer")
        print("-" * 85)
        for item in ports:
            print(f"{item['port']:<22} {item['description']:<36} {item['manufacturer']}")
        return 0

    def connect(self, port: str, baudrate: int, slave_id: int) -> None:
        if not port:
            raise ValueError("--port is required for this command")
        handler = SerialPortHandler(port, baudrate)
        if not handler.connect():
            raise RuntimeError(f"Unable to open {port}. Check the cable and dialout permission.")
        self.serial_handler = handler
        self.modbus = ModbusRTU(handler, slave_id=slave_id)
        print(f"Connected to {port} at {baudrate} baud (slave {slave_id})", file=sys.stderr)

    def disconnect(self) -> None:
        if self.serial_handler:
            self.serial_handler.disconnect()
            print("Disconnected", file=sys.stderr)
        self.serial_handler = None
        self.modbus = None

    def read_holding_registers(self, start: int, count: int) -> List[Dict[str, Any]]:
        if not self.modbus:
            raise RuntimeError("Not connected")
        values = self.modbus.read_holding_registers(start, count)
        if values is None:
            raise RuntimeError("No valid Modbus response received")
        timestamp = datetime.now().isoformat(timespec="seconds")
        return [
            {
                "address": start + index,
                "hex": f"0x{value:04X}",
                "unsigned": value,
                "signed": value if value < 32768 else value - 65536,
                "timestamp": timestamp,
            }
            for index, value in enumerate(values)
        ]

    @staticmethod
    def print_records(records: List[Dict[str, Any]]) -> None:
        print(f"{'Address':<10} {'Hex':<10} {'Unsigned':<12} {'Signed':<12} Timestamp")
        print("-" * 74)
        for item in records:
            print(
                f"{item['address']:<10} {item['hex']:<10} "
                f"{item['unsigned']:<12} {item['signed']:<12} {item['timestamp']}"
            )

    @staticmethod
    def save_records(path: str, records: List[Dict[str, Any]]) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix.lower() == ".json":
            output.write_text(json.dumps(records, indent=2), encoding="utf-8")
        elif output.suffix.lower() == ".csv":
            with output.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
        else:
            raise ValueError("Output filename must end in .csv or .json")
        print(f"Saved {len(records)} record(s) to {output}", file=sys.stderr)

    def write_register(self, address: int, value: int) -> None:
        if not self.modbus:
            raise RuntimeError("Not connected")
        if not self.modbus.write_single_register(address, value):
            raise RuntimeError("Write was not acknowledged by the Modbus device")
        print(f"Wrote {value} to holding register {address}")

    def scan(self, start: int, count: int, interval: float, output: Optional[str]) -> None:
        if interval < 0.05:
            raise ValueError("Scan interval must be at least 0.05 seconds")
        captured: List[Dict[str, Any]] = []
        print("Press Ctrl+C to stop", file=sys.stderr)
        try:
            while True:
                records = self.read_holding_registers(start, count)
                self.print_records(records)
                print()
                captured.extend(records)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("Scan stopped", file=sys.stderr)
        finally:
            if output and captured:
                self.save_records(output, captured)

    def show_stats(self) -> None:
        if not self.serial_handler:
            raise RuntimeError("Not connected")
        stats = self.serial_handler.get_stats()
        for key, value in stats.items():
            print(f"{key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serial Communication Monitor (Modbus RTU)")
    parser.add_argument("-p", "--port", help="Serial port, for example /dev/ttyUSB0")
    parser.add_argument("-b", "--baudrate", type=int, default=9600)
    parser.add_argument("--slave-id", type=int, default=1, help="Modbus slave ID (1-247)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-ports", help="List detected serial ports")

    read_parser = subparsers.add_parser("read-registers", help="Read holding registers")
    read_parser.add_argument("start", type=int)
    read_parser.add_argument("count", type=int)
    read_parser.add_argument("-o", "--output", help="Optional .csv or .json output file")

    write_parser = subparsers.add_parser("write-register", help="Write one holding register")
    write_parser.add_argument("address", type=int)
    write_parser.add_argument("value", type=int)

    scan_parser = subparsers.add_parser("scan", help="Continuously read holding registers")
    scan_parser.add_argument("start", type=int)
    scan_parser.add_argument("count", type=int)
    scan_parser.add_argument("-i", "--interval", type=float, default=1.0)
    scan_parser.add_argument("-o", "--output", help="Save captured records on exit (.csv or .json)")

    subparsers.add_parser("stats", help="Show connection statistics")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    cli = SerialMonitorCLI()

    if args.command == "list-ports":
        return cli.list_ports()

    try:
        cli.connect(args.port, args.baudrate, args.slave_id)
        if args.command == "read-registers":
            records = cli.read_holding_registers(args.start, args.count)
            cli.print_records(records)
            if args.output:
                cli.save_records(args.output, records)
        elif args.command == "write-register":
            cli.write_register(args.address, args.value)
        elif args.command == "scan":
            cli.scan(args.start, args.count, args.interval, args.output)
        elif args.command == "stats":
            cli.show_stats()
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        cli.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
