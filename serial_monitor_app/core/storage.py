#!/usr/bin/env python3
"""JSON, CSV, and SQLite persistence helpers."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FileStorage:
    """Save and load files below a configured data directory."""

    def __init__(self, base_path: str = "./data") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, filename: str) -> Path:
        path = self.base_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, filename: str, data: Dict[str, Any]) -> bool:
        filepath = self._path(filename)
        try:
            with filepath.open("w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, default=str, ensure_ascii=False)
            logger.info("Saved JSON to %s", filepath)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.error("Failed to save JSON %s: %s", filepath, exc)
            return False

    def load_json(self, filename: str) -> Optional[Dict[str, Any]]:
        filepath = self._path(filename)
        try:
            with filepath.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            logger.warning("JSON file does not exist: %s", filepath)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load JSON %s: %s", filepath, exc)
        return None

    def save_csv(self, filename: str, data: List[Dict[str, Any]]) -> bool:
        if not data:
            logger.warning("CSV export skipped because there is no data")
            return False
        filepath = self._path(filename)
        try:
            fieldnames = list(data[0].keys())
            with filepath.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(data)
            logger.info("Saved CSV to %s", filepath)
            return True
        except OSError as exc:
            logger.error("Failed to save CSV %s: %s", filepath, exc)
            return False

    def load_csv(self, filename: str) -> List[Dict[str, Any]]:
        filepath = self._path(filename)
        try:
            with filepath.open("r", encoding="utf-8", newline="") as file:
                return list(csv.DictReader(file))
        except FileNotFoundError:
            logger.warning("CSV file does not exist: %s", filepath)
        except OSError as exc:
            logger.error("Failed to load CSV %s: %s", filepath, exc)
        return []


class DatabaseStorage:
    """Store readings and alarms in SQLite."""

    def __init__(self, db_path: str = "./data/monitor.db") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self.init_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def init_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    address INTEGER NOT NULL,
                    label TEXT,
                    raw_value INTEGER,
                    scaled_value REAL,
                    unit TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    in_alarm INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS alarms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    address INTEGER NOT NULL,
                    label TEXT,
                    value REAL,
                    threshold REAL,
                    severity TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    event_type TEXT,
                    description TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_device_time ON readings(device_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_address_time ON readings(address, timestamp);
                """
            )
        logger.info("Database initialized at %s", self.db_path)

    def save_reading(self, device_id: str, address: int, label: str, raw_value: int, scaled_value: float, unit: str, in_alarm: bool = False) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO readings
                (device_id, address, label, raw_value, scaled_value, unit, in_alarm)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, address, label, raw_value, scaled_value, unit, int(in_alarm)),
            )

    def save_alarm(self, device_id: str, address: int, label: str, value: float, threshold: float, severity: str = "WARNING") -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO alarms
                (device_id, address, label, value, threshold, severity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (device_id, address, label, value, threshold, severity),
            )

    def get_readings(self, device_id: Optional[str] = None, address: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM readings WHERE 1=1"
        params: List[Any] = []
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        if address is not None:
            query += " AND address = ?"
            params.append(address)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, min(int(limit), 10000)))
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_alarms(self, device_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM alarms WHERE 1=1"
        params: List[Any] = []
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, min(int(limit), 10000)))
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]
