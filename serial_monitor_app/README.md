# Serial Communication Monitor for Linux and Windows

A Python application for communicating with serial devices and monitoring **Modbus RTU** registers. It includes a Tkinter desktop GUI, command-line interface, and a REST API intended for local engineering and test use.

## Implemented features

- Linux and Windows serial-port discovery using `pyserial`
- Modbus RTU CRC validation and exception handling
- Holding-register and input-register reads
- Coil reads
- Single and multiple holding-register writes
- Handling of fragmented serial responses
- Register labels, scale, offset, units, alarm flags, and statistics
- GUI manual read and one-second auto scan
- CSV and JSON export of captured values
- SQLite history storage
- REST endpoints for ports, connections, registers, mappings, history, and status

## Not implemented

The project does **not** currently implement Modbus TCP, charts, scripting, arbitrary generic-serial terminal mode, or simultaneous multi-device monitoring in the GUI. Earlier documentation incorrectly claimed those features existed.

## Windows portable application

A ready-to-use Windows x64 ZIP is built automatically from the `main` branch.

Download it from the repository's **Releases** page:

1. Open the latest prerelease named **Windows Portable App - Latest**.
2. Download `SerialCommunicationMonitor-Windows-x64.zip`.
3. Extract the ZIP to a normal writable folder.
4. Double-click `SerialCommunicationMonitor.exe`.

Python installation is not required. The ZIP also contains `START_HERE.txt`, this README, and the MIT license.

Windows may require the correct USB converter driver, such as FTDI, CH340/CH341, CP210x, or Prolific. Because the executable is not code-signed, Microsoft Defender SmartScreen may display a warning.

The executable is rebuilt by `.github/workflows/windows-portable.yml`. The workflow runs protocol tests, builds with PyInstaller, verifies that the executable remains running during startup, uploads a 90-day workflow artifact, and replaces the rolling `windows-latest` prerelease.

## Linux installation

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk

git clone https://github.com/nandurpm/Serial_Communication.git
cd Serial_Communication/serial_monitor_app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Serial-port permission

On Debian, Ubuntu, and Linux Mint, add your user to the `dialout` group:

```bash
sudo usermod -aG dialout "$USER"
```

Log out and log back in after running that command. Do not run the application permanently with `sudo` just to access `/dev/ttyUSB*`.

## Run from source

### GUI

```bash
python app_gui.py
```

### CLI

```bash
python app_cli.py --help
```

### REST API

```bash
python app_api.py
```

The API binds to `127.0.0.1:5000` by default. Configuration variables:

```bash
export SERIAL_MONITOR_HOST=127.0.0.1
export SERIAL_MONITOR_PORT=5000
export SERIAL_MONITOR_DEBUG=0
export SERIAL_MONITOR_CORS_ORIGINS=http://localhost:3000
```

Do not expose the API to an untrusted network. It can write values to connected control equipment.

## GUI workflow

1. Connect the USB-to-RS485 or USB-to-serial converter.
2. Select the detected port, baudrate, and Modbus slave ID.
3. Click **Connect**.
4. Enter the first register address and quantity.
5. Click **Read** or **Start Auto Scan**.
6. Add mappings for engineering labels, scaling, offset, and units.
7. Export captured records from the **Data Log** tab.

Unmapped registers are still displayed with their raw values.

## Mapping configuration

`config/mappings.json` uses numeric register addresses:

```json
{
  "mappings": [
    {
      "device_id": "device_1",
      "address": 0,
      "label": "Drive temperature",
      "data_type": "int16",
      "scale": 0.1,
      "offset": 0,
      "unit": "°C",
      "alarm_threshold": 80
    }
  ]
}
```

## REST examples

List ports:

```bash
curl http://127.0.0.1:5000/api/ports
```

Connect:

```bash
curl -X POST http://127.0.0.1:5000/api/connections \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"escalator_controller","port":"/dev/ttyUSB0","baudrate":9600,"slave_id":1}'
```

Read ten holding registers:

```bash
curl 'http://127.0.0.1:5000/api/registers?device_id=escalator_controller&start=0&count=10'
```

Write one holding register:

```bash
curl -X POST http://127.0.0.1:5000/api/registers \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"escalator_controller","address":10,"value":1}'
```

Disconnect:

```bash
curl -X DELETE 'http://127.0.0.1:5000/api/connections?device_id=escalator_controller'
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The protocol tests use a fake serial handler, so they do not require connected hardware.

## Engineering warning

Register writes can change controller behavior. Verify the device register map, slave ID, baudrate, parity, stop bits, and permitted operating state before writing. This software is not a certified escalator safety controller or safety test instrument.
