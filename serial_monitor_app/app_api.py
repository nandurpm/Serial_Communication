#!/usr/bin/env python3
"""
REST API Server
Flask-based API for remote serial communication monitoring.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_restful import Api, Resource
import logging
from typing import Dict, Any

from core.serial_handler import SerialPortHandler, SerialPortFinder
from core.modbus_protocol import ModbusRTU
from core.data_mapper import DataMapper, AddressMap, DataType
from core.storage import DatabaseStorage
from core.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
api = Api(app)

# Global state
serial_handlers: Dict[str, SerialPortHandler] = {}
modbus_clients: Dict[str, ModbusRTU] = {}
mapper = DataMapper()
db_storage = DatabaseStorage()


class PortListResource(Resource):
    """List available serial ports."""

    def get(self):
        """GET /api/ports"""
        finder = SerialPortFinder()
        ports = finder.list_ports()
        return {"status": "success", "ports": ports}


class ConnectionResource(Resource):
    """Manage serial connections."""

    def post(self):
        """POST /api/connections - Connect to port"""
        data = request.get_json()
        port = data.get("port")
        baudrate = data.get("baudrate", 9600)
        device_id = data.get("device_id", port)

        try:
            handler = SerialPortHandler(port, baudrate)
            if handler.connect():
                serial_handlers[device_id] = handler
                modbus_clients[device_id] = ModbusRTU(handler)
                logger.info(f"Connected device: {device_id}")
                return {
                    "status": "success",
                    "message": f"Connected to {port}",
                    "device_id": device_id
                }, 200
        except Exception as e:
            return {"status": "error", "message": str(e)}, 400

    def delete(self):
        """DELETE /api/connections/:device_id - Disconnect"""
        device_id = request.args.get("device_id")
        if device_id in serial_handlers:
            serial_handlers[device_id].disconnect()
            del serial_handlers[device_id]
            del modbus_clients[device_id]
            return {"status": "success", "message": f"Disconnected {device_id}"}
        return {"status": "error", "message": "Device not found"}, 404

    def get(self):
        """GET /api/connections - List active connections"""
        connections = list(serial_handlers.keys())
        return {
            "status": "success",
            "connections": connections,
            "count": len(connections)
        }


class RegistersResource(Resource):
    """Read/Write registers."""

    def get(self):
        """GET /api/registers - Read registers"""
        device_id = request.args.get("device_id")
        start = int(request.args.get("start", 0))
        count = int(request.args.get("count", 10))

        if device_id not in modbus_clients:
            return {"status": "error", "message": "Device not connected"}, 404

        try:
            modbus = modbus_clients[device_id]
            data = modbus.read_holding_registers(start, count)
            if data:
                return {
                    "status": "success",
                    "device_id": device_id,
                    "start_address": start,
                    "registers": data
                }
            return {"status": "error", "message": "Read failed"}, 400
        except Exception as e:
            return {"status": "error", "message": str(e)}, 400

    def post(self):
        """POST /api/registers - Write register"""
        data = request.get_json()
        device_id = data.get("device_id")
        address = data.get("address")
        value = data.get("value")

        if device_id not in modbus_clients:
            return {"status": "error", "message": "Device not connected"}, 404

        try:
            modbus = modbus_clients[device_id]
            if modbus.write_single_register(address, value):
                return {
                    "status": "success",
                    "message": f"Wrote {value} to {address}",
                    "device_id": device_id
                }
            return {"status": "error", "message": "Write failed"}, 400
        except Exception as e:
            return {"status": "error", "message": str(e)}, 400


class MappingsResource(Resource):
    """Manage address mappings."""

    def get(self):
        """GET /api/mappings - Get all mappings"""
        device_id = request.args.get("device_id")
        mappings = mapper.get_all_mappings(device_id)
        return {
            "status": "success",
            "mappings": {
                k: {
                    "address": v.address,
                    "label": v.label,
                    "data_type": v.data_type.value,
                    "scale": v.scale,
                    "unit": v.unit
                }
                for k, v in mappings.items()
            }
        }

    def post(self):
        """POST /api/mappings - Add mapping"""
        data = request.get_json()
        mapping = AddressMap(
            device_id=data.get("device_id"),
            address=data.get("address"),
            label=data.get("label"),
            data_type=DataType(data.get("data_type", "uint16")),
            scale=data.get("scale", 1.0),
            unit=data.get("unit", "")
        )
        mapper.add_mapping(mapping)
        return {"status": "success", "message": "Mapping added"}


class StatisticsResource(Resource):
    """Get statistics."""

    def get(self):
        """GET /api/statistics"""
        device_id = request.args.get("device_id")
        address = int(request.args.get("address"))

        stats = mapper.get_statistics(device_id, address)
        if stats:
            return {"status": "success", "statistics": stats}
        return {"status": "error", "message": "No data"}, 404


class HistoryResource(Resource):
    """Get value history."""

    def get(self):
        """GET /api/history"""
        device_id = request.args.get("device_id")
        address = int(request.args.get("address"))
        limit = int(request.args.get("limit", 100))

        history = mapper.get_history(device_id, address, limit)
        return {"status": "success", "history": history}


class StatusResource(Resource):
    """Get application status."""

    def get(self):
        """GET /api/status"""
        return {
            "status": "running",
            "connected_devices": list(serial_handlers.keys()),
            "total_mappings": len(mapper.get_all_mappings()),
            "version": "1.0.0"
        }


# Register resources
api.add_resource(PortListResource, '/api/ports')
api.add_resource(ConnectionResource, '/api/connections')
api.add_resource(RegistersResource, '/api/registers')
api.add_resource(MappingsResource, '/api/mappings')
api.add_resource(StatisticsResource, '/api/statistics')
api.add_resource(HistoryResource, '/api/history')
api.add_resource(StatusResource, '/api/status')


@app.errorhandler(404)
def not_found(e):
    return {"status": "error", "message": "Not found"}, 404


@app.errorhandler(500)
def internal_error(e):
    return {"status": "error", "message": "Internal server error"}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
