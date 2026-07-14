#!/usr/bin/env python3
"""
Storage Module
Handles data persistence to file and database.
"""

import json
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)


class FileStorage:
    """Save and load data from files."""

    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_json(self, filename: str, data: Dict[str, Any]):
        """Save data to JSON file."""
        filepath = self.base_path / filename
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save JSON: {e}")

    def load_json(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load data from JSON file."""
        filepath = self.base_path / filename
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            logger.info(f"Loaded from {filepath}")
            return data
        except Exception as e:
            logger.error(f"Failed to load JSON: {e}")
            return None

    def save_csv(self, filename: str, data: List[Dict[str, Any]]):
        """Save data to CSV file."""
        if not data:
            return

        filepath = self.base_path / filename
        try:
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            logger.info(f"Saved CSV to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save CSV: {e}")

    def load_csv(self, filename: str) -> List[Dict[str, Any]]:
        """Load data from CSV file."""
        filepath = self.base_path / filename
        data = []
        try:
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                data = list(reader)
            logger.info(f"Loaded CSV from {filepath}")
        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
        return data


class DatabaseStorage:
    """Save and load data from SQLite database."""

    def __init__(self, db_path: str = "./data/monitor.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Readings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                address INTEGER NOT NULL,
                label TEXT,
                raw_value INTEGER,
                scaled_value REAL,
                unit TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                in_alarm BOOLEAN DEFAULT 0
            )
        ''')

        # Alarms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                address INTEGER NOT NULL,
                label TEXT,
                value REAL,
                threshold REAL,
                severity TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                event_type TEXT,
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_device_time ON readings(device_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_address_time ON readings(address, timestamp)')

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def save_reading(
        self,
        device_id: str,
        address: int,
        label: str,
        raw_value: int,
        scaled_value: float,
        unit: str,
        in_alarm: bool = False
    ):
        """Save reading to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO readings
            (device_id, address, label, raw_value, scaled_value, unit, in_alarm)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, address, label, raw_value, scaled_value, unit, in_alarm))
        conn.commit()
        conn.close()

    def save_alarm(
        self,
        device_id: str,
        address: int,
        label: str,
        value: float,
        threshold: float,
        severity: str = "WARNING"
    ):
        """Save alarm to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alarms
            (device_id, address, label, value, threshold, severity)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (device_id, address, label, value, threshold, severity))
        conn.commit()
        conn.close()

    def get_readings(
        self,
        device_id: str = None,
        address: int = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get readings from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM readings WHERE 1=1"
        params = []

        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        if address is not None:
            query += " AND address = ?"
            params.append(address)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_alarms(
        self,
        device_id: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get alarms from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM alarms WHERE 1=1"
        params = []

        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
