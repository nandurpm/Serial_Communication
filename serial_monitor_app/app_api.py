#!/usr/bin/env python3
"""REST API for serial and Modbus RTU monitoring."""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any, Dict, Tuple

from flask import Flask, request
from flask_cors import CORS
from flask_restful import Api, Resource

from core.data_mapper import AddressMap, DataMapper, DataType
from core.modbus_protocol import ModbusRTU
from core.serial_handler import SerialPortFinder, SerialPortHandler
from core.storage import DatabaseStorage
from core.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
allowed_origins = os.getenv("SERIAL_MONITOR_CORS_ORIGINS", "http://localhost:*").split(",")
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
api = Api(app)

serial_handlers: Dict[str, SerialPortHandler] = {}
modbus_clients: Dict[str, ModbusRTU] = {}
mapper = DataMapper()
db_storage = DatabaseStorage()
state_lock = threading.RLock()


def error(message: str, status: int = 400) -> Tuple[Dict[str, Any], int]:
    return {"status": "error", "message": message}, status


def json_body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    return data


def integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


class PortListResource(Resource):
    def get(self):
        return {"status": "success", "ports": SerialPortFinder.list_ports()}


class ConnectionResource(Resource):
    def post(self):
        try:
            data = json_body()
            port = str(data.get("port", "")).strip()
            if not port:
                raise ValueError("port is required")
            baudrate = integer(data.get("baudrate", 9600), "baudrate", 1, 4_000_000)
            slave_id = integer(data.get("slave_id", 1), "slave_id", 1, 247)
            device_id = str(data.get("device_id") or port).strip()
            if not device_id:
                raise ValueError("device_id cannot be empty")

            with state_lock:
                if device_id in serial_handlers:
                    return error("device_id is already connected", 409)
                handler = SerialPortHandler(port, baudrate)
                if not handler.connect():
                    return error(f"Unable to open serial port {port}", 400)
                serial_handlers[device_id] = handler
                modbus_clients[device_id] = ModbusRTU(handler, slave_id=slave_id)

            logger.info("Connected device %s on %s", device_id, port)
            return {
                "status": "success",
                "message": f"Connected to {port}",
                "device_id": device_id,
                "slave_id": slave_id,
            }, 201
        except ValueError as exc:
            return error(str(exc))
        except Exception as exc:
            logger.exception("Connection creation failed")
            return error(str(exc), 500)

    def delete(self):
        device_id = str(request.args.get("device_id", "")).strip()
        if not device_id:
            return error("device_id is required")
        with state_lock:
            handler = serial_handlers.pop(device_id, None)
            modbus_clients.pop(device_id, None)
        if not handler:
            return error("Device not found", 404)
        handler.disconnect()
        return {"status": "success", "message": f"Disconnected {device_id}"}

    def get(self):
        with state_lock:
            connections = [
                {
                    "device_id": device_id,
                    "port": handler.port,
                    "baudrate": handler.baudrate,
                    "connected": handler.is_connected,
                    "stats": handler.get_stats(),
                }
                for device_id, handler in serial_handlers.items()
            ]
        return {"status": "success", "connections": connections, "count": len(connections)}


class RegistersResource(Resource):
    def get(self):
        try:
            device_id = str(request.args.get("device_id", "")).strip()
            start = integer(request.args.get("start", 0), "start", 0, 65535)
            count = integer(request.args.get("count", 10), "count", 1, 125)
            if start + count - 1 > 65535:
                raise ValueError("Requested register range exceeds 65535")
            with state_lock:
                modbus = modbus_clients.get(device_id)
            if not modbus:
                return error("Device not connected", 404)
            values = modbus.read_holding_registers(start, count)
            if values is None:
                return error("No valid Modbus response received", 504)

            mapped = []
            for offset, raw_value in enumerate(values):
                address = start + offset
                item = mapper.map_value(device_id, address, raw_value)
                mapped.append(item or {"device_id": device_id, "address": address, "raw_value": raw_value})
                if item:
                    db_storage.save_reading(
                        device_id,
                        address,
                        item["label"],
                        raw_value,
                        item["scaled_value"],
                        item["unit"],
                        item["in_alarm"],
                    )
            return {
                "status": "success",
                "device_id": device_id,
                "start_address": start,
                "registers": values,
                "mapped": mapped,
            }
        except ValueError as exc:
            return error(str(exc))
        except Exception as exc:
            logger.exception("Register read failed")
            return error(str(exc), 500)

    def post(self):
        try:
            data = json_body()
            device_id = str(data.get("device_id", "")).strip()
            address = integer(data.get("address"), "address", 0, 65535)
            value = integer(data.get("value"), "value", 0, 65535)
            with state_lock:
                modbus = modbus_clients.get(device_id)
            if not modbus:
                return error("Device not connected", 404)
            if not modbus.write_single_register(address, value):
                return error("Write was not acknowledged by the Modbus device", 504)
            return {
                "status": "success",
                "message": f"Wrote {value} to register {address}",
                "device_id": device_id,
            }
        except ValueError as exc:
            return error(str(exc))
        except Exception as exc:
            logger.exception("Register write failed")
            return error(str(exc), 500)


class MappingsResource(Resource):
    def get(self):
        device_id = request.args.get("device_id")
        mappings = mapper.get_all_mappings(device_id)
        return {
            "status": "success",
            "mappings": {
                key: {
                    "device_id": value.device_id,
                    "address": value.address,
                    "label": value.label,
                    "data_type": value.data_type.value,
                    "scale": value.scale,
                    "offset": value.offset,
                    "unit": value.unit,
                }
                for key, value in mappings.items()
            },
        }

    def post(self):
        try:
            data = json_body()
            device_id = str(data.get("device_id", "")).strip()
            label = str(data.get("label", "")).strip()
            if not device_id or not label:
                raise ValueError("device_id and label are required")
            mapping = AddressMap(
                device_id=device_id,
                address=integer(data.get("address"), "address", 0, 65535),
                label=label,
                data_type=DataType(data.get("data_type", "uint16")),
                scale=float(data.get("scale", 1.0)),
                offset=float(data.get("offset", 0.0)),
                unit=str(data.get("unit", "")),
                alarm_threshold=data.get("alarm_threshold"),
            )
            mapper.add_mapping(mapping)
            return {"status": "success", "message": "Mapping added"}, 201
        except (ValueError, TypeError) as exc:
            return error(str(exc))


class StatisticsResource(Resource):
    def get(self):
        try:
            device_id = str(request.args.get("device_id", "")).strip()
            address = integer(request.args.get("address"), "address", 0, 65535)
            stats = mapper.get_statistics(device_id, address)
            if not stats:
                return error("No data", 404)
            return {"status": "success", "statistics": stats}
        except ValueError as exc:
            return error(str(exc))


class HistoryResource(Resource):
    def get(self):
        try:
            device_id = str(request.args.get("device_id", "")).strip()
            address = integer(request.args.get("address"), "address", 0, 65535)
            limit = integer(request.args.get("limit", 100), "limit", 1, 10000)
            return {"status": "success", "history": mapper.get_history(device_id, address, limit)}
        except ValueError as exc:
            return error(str(exc))


class StatusResource(Resource):
    def get(self):
        with state_lock:
            devices = list(serial_handlers.keys())
        return {
            "status": "running",
            "connected_devices": devices,
            "total_mappings": len(mapper.get_all_mappings()),
            "version": "1.1.0",
        }


api.add_resource(PortListResource, "/api/ports")
api.add_resource(ConnectionResource, "/api/connections")
api.add_resource(RegistersResource, "/api/registers")
api.add_resource(MappingsResource, "/api/mappings")
api.add_resource(StatisticsResource, "/api/statistics")
api.add_resource(HistoryResource, "/api/history")
api.add_resource(StatusResource, "/api/status")


@app.errorhandler(404)
def not_found(_exception):
    return error("Not found", 404)


@app.errorhandler(500)
def internal_error(_exception):
    return error("Internal server error", 500)


def shutdown_connections() -> None:
    with state_lock:
        handlers = list(serial_handlers.values())
        serial_handlers.clear()
        modbus_clients.clear()
    for handler in handlers:
        handler.disconnect()


atexit.register(shutdown_connections)


def main() -> None:
    host = os.getenv("SERIAL_MONITOR_HOST", "127.0.0.1")
    port = int(os.getenv("SERIAL_MONITOR_PORT", "5000"))
    debug = os.getenv("SERIAL_MONITOR_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
