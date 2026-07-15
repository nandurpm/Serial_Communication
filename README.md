# Serial Communication Monitor

Linux desktop, CLI, and REST tools for serial communication with Modbus RTU devices.

The application source is in [`serial_monitor_app/`](serial_monitor_app/). See its README for installation, Linux serial-port permissions, usage, API endpoints, and current limitations.

## Current status

This repository now provides:

- Safe serial-port discovery without opening or locking devices
- Modbus RTU holding/input-register and coil reads
- Single and multiple holding-register writes
- CRC, slave-ID, function-code, frame-length, and timeout validation
- Tkinter GUI with live reads, auto scan, address mappings, CSV/JSON export, statistics, and SQLite history
- CLI and local REST API entry points
- Hardware-free protocol tests

Modbus TCP, scripting, charts, and a multi-device GUI are **not implemented**. Earlier documentation incorrectly claimed those features existed.
