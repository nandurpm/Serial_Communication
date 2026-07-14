# Serial Communication Monitoring App (Linux)

A comprehensive serial communication monitoring application for Linux with real-time Modbus protocol support, address mapping, and data visualization.

## Features

### Core Features
- **Multi-Protocol Support**: Modbus RTU, Modbus TCP, Generic Serial
- **Real-Time Monitoring**: Live data capture and display
- **Address Mapping**: Map RX values to registers and labels
- **Data Visualization**: Charts and graphs for trend analysis
- **Device Configuration**: Easy device setup and management
- **Hex/ASCII Display**: Toggle between hex and ASCII representation
- **Data Logging**: Export data to CSV/JSON
- **Error Detection**: CRC validation and error reporting

### Advanced Features
- **Multi-Device Support**: Monitor multiple devices simultaneously
- **Alarm Management**: Set thresholds and alerts
- **Statistics**: Real-time min/max/avg calculations
- **Scripting**: Custom command sequences
- **Database Integration**: Store historical data
- **REST API**: Remote monitoring capabilities

## Installation

### Prerequisites
```bash
sudo apt-get update
sudo apt-get install python3 python3-pip python3-tk
sudo apt-get install libgpiod-dev
```

### Setup
```bash
cd serial_monitor_app
pip3 install -r requirements.txt
```

## Quick Start

### GUI Application
```bash
python3 app_gui.py
```

### CLI Application
```bash
python3 app_cli.py
```

### API Server
```bash
python3 app_api.py
```

## Directory Structure

```
serial_monitor_app/
├── app_gui.py                 # Main GUI application (Tkinter)
├── app_cli.py                 # Command-line interface
├── app_api.py                 # REST API server
├── core/
│   ├── serial_handler.py      # Serial port management
│   ├── modbus_protocol.py     # Modbus RTU/TCP implementation
│   ├── data_mapper.py         # Address mapping engine
│   ├── storage.py             # Database and file storage
│   └── utils.py               # Utility functions
├── ui/
│   ├── main_window.py         # Main UI window
│   ├── device_panel.py        # Device configuration
│   ├── monitor_panel.py       # Real-time monitoring
│   ├── chart_panel.py         # Data visualization
│   └── styles.py              # UI themes
├── config/
│   ├── default_config.json    # Default configuration
│   ├── devices.json           # Device definitions
│   └── mappings.json          # Address mappings
├── tests/
│   ├── test_serial.py
│   ├── test_modbus.py
│   └── test_mapper.py
├── requirements.txt
└── setup.py
```

## Configuration

### Device Configuration (devices.json)
```json
{
  "devices": [
    {
      "id": "device_1",
      "name": "PLC-01",
      "type": "modbus_rtu",
      "port": "/dev/ttyUSB0",
      "baudrate": 9600,
      "parity": "N",
      "stopbits": 1,
      "slave_id": 1
    }
  ]
}
```

### Address Mapping (mappings.json)
```json
{
  "mappings": [
    {
      "device_id": "device_1",
      "address": "holding_register_0",
      "label": "Temperature Sensor",
      "data_type": "int16",
      "scale": 0.1,
      "offset": -40,
      "unit": "°C",
      "description": "Main temperature reading"
    }
  ]
}
```

## Usage Examples

### Python API
```python
from core.serial_handler import SerialPortHandler
from core.modbus_protocol import ModbusRTU

# Initialize serial handler
handler = SerialPortHandler('/dev/ttyUSB0', 9600)

# Initialize Modbus
modbus = ModbusRTU(handler, slave_id=1)

# Read holding registers
data = modbus.read_holding_registers(0, 10)
```

## Support & Documentation

- **User Guide**: See `docs/user_guide.md`
- **API Reference**: See `docs/api_reference.md`
- **Examples**: See `examples/` directory
- **Issues**: Report on GitHub Issues

## License

MIT License
