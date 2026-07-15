#!/usr/bin/env python3
"""Tkinter GUI for the serial communication monitor."""

from __future__ import annotations

import csv
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.data_mapper import AddressMap, DataMapper, DataType
from core.modbus_protocol import ModbusRTU
from core.serial_handler import SerialPortFinder, SerialPortHandler
from core.storage import DatabaseStorage
from core.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent


class SerialMonitorApp:
    """Desktop interface for Modbus RTU register monitoring."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Serial Communication Monitor")
        self.root.geometry("1180x720")
        self.root.minsize(900, 600)

        self.serial_handler: SerialPortHandler | None = None
        self.modbus: ModbusRTU | None = None
        self.mapper = DataMapper()
        self.db_storage = DatabaseStorage(str(Path.home() / ".local" / "share" / "serial-monitor" / "monitor.db"))
        self.records: List[Dict[str, Any]] = []
        self.auto_scan_enabled = False
        self.read_in_progress = False

        self._setup_ui()
        self._load_configuration()
        self._refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_ui(self) -> None:
        top_frame = ttk.LabelFrame(self.root, text="Connection Settings", padding=10)
        top_frame.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(top_frame, text="Port:").pack(side=tk.LEFT, padx=(0, 5))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(top_frame, textvariable=self.port_var, width=22, state="readonly")
        self.port_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(top_frame, text="Baudrate:").pack(side=tk.LEFT, padx=(12, 5))
        self.baudrate_var = tk.StringVar(value="9600")
        self.baudrate_combo = ttk.Combobox(
            top_frame,
            textvariable=self.baudrate_var,
            values=["300", "600", "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
            width=10,
            state="readonly",
        )
        self.baudrate_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(top_frame, text="Slave ID:").pack(side=tk.LEFT, padx=(12, 5))
        self.slave_id_var = tk.StringVar(value="1")
        ttk.Spinbox(top_frame, from_=1, to=247, textvariable=self.slave_id_var, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame, text="Refresh Ports", command=self._refresh_ports).pack(side=tk.LEFT, padx=8)
        self.connect_btn = ttk.Button(top_frame, text="Connect", command=self._connect)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        self.disconnect_btn = ttk.Button(top_frame, text="Disconnect", command=self._disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(top_frame, text="Status: Disconnected", foreground="red")
        self.status_label.pack(side=tk.RIGHT, padx=5)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.monitor_tab = ttk.Frame(notebook)
        notebook.add(self.monitor_tab, text="Real-Time Monitor")
        self._setup_monitor_tab()

        mapping_tab = ttk.Frame(notebook)
        notebook.add(mapping_tab, text="Address Mapping")
        self._setup_mapping_tab(mapping_tab)

        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Data Log")
        self._setup_log_tab(log_tab)

        stats_tab = ttk.Frame(notebook)
        notebook.add(stats_tab, text="Statistics")
        self._setup_stats_tab(stats_tab)

    def _setup_monitor_tab(self) -> None:
        ctrl_frame = ttk.Frame(self.monitor_tab)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=8)

        ttk.Label(ctrl_frame, text="Device ID:").pack(side=tk.LEFT, padx=5)
        self.device_var = tk.StringVar(value="device_1")
        self.device_combo = ttk.Combobox(ctrl_frame, textvariable=self.device_var, width=18)
        self.device_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Start Address:").pack(side=tk.LEFT, padx=(15, 5))
        self.start_addr_var = tk.StringVar(value="0")
        ttk.Entry(ctrl_frame, textvariable=self.start_addr_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Quantity:").pack(side=tk.LEFT, padx=(15, 5))
        self.qty_var = tk.StringVar(value="10")
        ttk.Entry(ctrl_frame, textvariable=self.qty_var, width=8).pack(side=tk.LEFT, padx=5)

        self.read_btn = ttk.Button(ctrl_frame, text="Read", command=self._read_registers)
        self.read_btn.pack(side=tk.LEFT, padx=8)
        self.auto_scan_btn = ttk.Button(ctrl_frame, text="Start Auto Scan", command=self._toggle_auto_scan)
        self.auto_scan_btn.pack(side=tk.LEFT, padx=5)

        tree_frame = ttk.Frame(self.monitor_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        x_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.data_tree = ttk.Treeview(
            tree_frame,
            columns=("Address", "Label", "Raw", "Scaled", "Unit", "Timestamp", "Alarm"),
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
            show="headings",
        )
        y_scroll.config(command=self.data_tree.yview)
        x_scroll.config(command=self.data_tree.xview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.data_tree.pack(fill=tk.BOTH, expand=True)

        widths = {"Address": 90, "Label": 220, "Raw": 100, "Scaled": 110, "Unit": 90, "Timestamp": 190, "Alarm": 80}
        for column, width in widths.items():
            self.data_tree.heading(column, text=column)
            self.data_tree.column(column, width=width, anchor=tk.CENTER)

    def _setup_mapping_tab(self, parent: ttk.Frame) -> None:
        config_frame = ttk.LabelFrame(parent, text="Add or Update Mapping", padding=12)
        config_frame.pack(fill=tk.X, padx=8, pady=8)

        fields = [
            ("Device ID", "mapping_device_entry", "device_1"),
            ("Label", "mapping_label_entry", ""),
            ("Address", "mapping_address_entry", "0"),
            ("Scale", "mapping_scale_entry", "1.0"),
            ("Offset", "mapping_offset_entry", "0.0"),
            ("Unit", "mapping_unit_entry", ""),
        ]
        for row, (label, attr, default) in enumerate(fields):
            ttk.Label(config_frame, text=f"{label}:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
            entry = ttk.Entry(config_frame, width=32)
            entry.insert(0, default)
            entry.grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)
            setattr(self, attr, entry)

        ttk.Label(config_frame, text="Data Type:").grid(row=2, column=2, sticky=tk.W, padx=20, pady=5)
        self.mapping_dtype_combo = ttk.Combobox(
            config_frame,
            values=[item.value for item in DataType],
            width=24,
            state="readonly",
        )
        self.mapping_dtype_combo.set(DataType.UINT16.value)
        self.mapping_dtype_combo.grid(row=2, column=3, sticky=tk.W, padx=5, pady=5)

        ttk.Button(config_frame, text="Save Mapping", command=self._save_mapping, width=20).grid(row=6, column=1, sticky=tk.W, padx=5, pady=12)

        self.mapping_tree = ttk.Treeview(
            parent,
            columns=("Device", "Address", "Label", "Type", "Scale", "Offset", "Unit"),
            show="headings",
            height=14,
        )
        for column in ("Device", "Address", "Label", "Type", "Scale", "Offset", "Unit"):
            self.mapping_tree.heading(column, text=column)
            self.mapping_tree.column(column, width=130, anchor=tk.CENTER)
        self.mapping_tree.column("Label", width=220, anchor=tk.W)
        self.mapping_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    def _setup_log_tab(self, parent: ttk.Frame) -> None:
        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=8)
        ttk.Button(ctrl_frame, text="Export CSV", command=self._export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Export JSON", command=self._export_json).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT, padx=5)
        self.log_text = tk.Text(parent, height=20, wrap=tk.NONE, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    def _setup_stats_tab(self, parent: ttk.Frame) -> None:
        self.stats_tree = ttk.Treeview(
            parent,
            columns=("Device", "Address", "Label", "Min", "Max", "Average", "Count", "Latest"),
            show="headings",
            height=20,
        )
        for column in ("Device", "Address", "Label", "Min", "Max", "Average", "Count", "Latest"):
            self.stats_tree.heading(column, text=column)
            self.stats_tree.column(column, width=115, anchor=tk.CENTER)
        self.stats_tree.column("Label", width=220, anchor=tk.W)
        self.stats_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _refresh_ports(self) -> None:
        try:
            ports = SerialPortFinder.list_ports()
            values = [item["port"] for item in ports]
            self.port_combo["values"] = values
            if values and self.port_var.get() not in values:
                self.port_var.set(values[0])
            elif not values:
                self.port_var.set("")
            self._append_log(f"Detected {len(values)} serial port(s)")
        except Exception as exc:
            logger.exception("Port discovery failed")
            messagebox.showerror("Port Discovery Error", str(exc))

    def _connect(self) -> None:
        try:
            port = self.port_var.get().strip()
            baudrate = int(self.baudrate_var.get())
            slave_id = int(self.slave_id_var.get())
            if not port:
                raise ValueError("Select a serial port first")
            handler = SerialPortHandler(port, baudrate)
            if not handler.connect():
                raise RuntimeError(f"Unable to open {port}. Check permissions and cable connection.")
            self.serial_handler = handler
            self.modbus = ModbusRTU(handler, slave_id=slave_id)
            self.status_label.config(text=f"Status: Connected to {port}", foreground="green")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self._append_log(f"Connected to {port} at {baudrate} baud, slave {slave_id}")
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Connection Error", str(exc))

    def _disconnect(self) -> None:
        self.auto_scan_enabled = False
        self.auto_scan_btn.config(text="Start Auto Scan")
        if self.serial_handler:
            self.serial_handler.disconnect()
        self.serial_handler = None
        self.modbus = None
        self.status_label.config(text="Status: Disconnected", foreground="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self._append_log("Disconnected")

    def _read_registers(self) -> None:
        self._start_read(show_errors=True)

    def _start_read(self, show_errors: bool) -> None:
        if self.read_in_progress:
            return
        if not self.modbus:
            if show_errors:
                messagebox.showerror("Read Error", "Connect to a serial device first")
            return
        try:
            start = int(self.start_addr_var.get())
            quantity = int(self.qty_var.get())
            if not 0 <= start <= 65535:
                raise ValueError("Start address must be between 0 and 65535")
            if not 1 <= quantity <= 125:
                raise ValueError("Quantity must be between 1 and 125")
            if start + quantity - 1 > 65535:
                raise ValueError("Requested register range exceeds 65535")
        except ValueError as exc:
            if show_errors:
                messagebox.showerror("Read Error", str(exc))
            return

        self.read_in_progress = True
        self.read_btn.config(state=tk.DISABLED)
        modbus = self.modbus

        def worker() -> None:
            try:
                data = modbus.read_holding_registers(start, quantity) if modbus else None
                self.root.after(0, lambda: self._finish_read(data, start, None))
            except Exception as exc:
                self.root.after(0, lambda error=exc: self._finish_read(None, start, error))

        threading.Thread(target=worker, name="modbus-read", daemon=True).start()

    def _finish_read(self, data: List[int] | None, start_address: int, error: Exception | None) -> None:
        self.read_in_progress = False
        self.read_btn.config(state=tk.NORMAL)
        if error:
            self._append_log(f"Read failed: {error}")
            if not self.auto_scan_enabled:
                messagebox.showerror("Read Error", str(error))
        elif data is None:
            self._append_log("Read failed: no valid Modbus response")
            if not self.auto_scan_enabled:
                messagebox.showerror("Read Error", "No valid Modbus response received")
        else:
            self._display_data(data, start_address)
            self._append_log(f"Read {len(data)} register(s) starting at {start_address}")

        if self.auto_scan_enabled:
            self.root.after(1000, lambda: self._start_read(show_errors=False))

    def _display_data(self, data: List[int], start_address: int) -> None:
        self.data_tree.delete(*self.data_tree.get_children())
        device_id = self.device_var.get().strip() or "device_1"
        timestamp = datetime.now().isoformat(timespec="seconds")

        for index, raw_value in enumerate(data):
            address = start_address + index
            mapped = self.mapper.map_value(device_id, address, raw_value)
            if mapped:
                record = mapped
            else:
                record = {
                    "device_id": device_id,
                    "address": address,
                    "label": "Unmapped",
                    "raw_value": raw_value,
                    "scaled_value": raw_value,
                    "unit": "",
                    "timestamp": timestamp,
                    "in_alarm": False,
                }

            self.records.append(record.copy())
            self.data_tree.insert(
                "",
                tk.END,
                values=(record["address"], record["label"], record["raw_value"], record["scaled_value"], record["unit"], record["timestamp"], "YES" if record["in_alarm"] else "NO"),
            )
            self.db_storage.save_reading(
                device_id=record["device_id"],
                address=record["address"],
                label=record["label"],
                raw_value=record["raw_value"],
                scaled_value=record["scaled_value"],
                unit=record["unit"],
                in_alarm=record["in_alarm"],
            )

        self._refresh_statistics()

    def _toggle_auto_scan(self) -> None:
        if not self.modbus:
            messagebox.showerror("Auto Scan", "Connect to a serial device first")
            return
        self.auto_scan_enabled = not self.auto_scan_enabled
        self.auto_scan_btn.config(text="Stop Auto Scan" if self.auto_scan_enabled else "Start Auto Scan")
        self._append_log("Auto scan started" if self.auto_scan_enabled else "Auto scan stopped")
        if self.auto_scan_enabled:
            self._start_read(show_errors=False)

    def _save_mapping(self) -> None:
        try:
            mapping = AddressMap(
                device_id=self.mapping_device_entry.get().strip() or "device_1",
                address=int(self.mapping_address_entry.get()),
                label=self.mapping_label_entry.get().strip(),
                data_type=DataType(self.mapping_dtype_combo.get()),
                scale=float(self.mapping_scale_entry.get()),
                offset=float(self.mapping_offset_entry.get()),
                unit=self.mapping_unit_entry.get().strip(),
            )
            if not mapping.label:
                raise ValueError("Label is required")
            if not 0 <= mapping.address <= 65535:
                raise ValueError("Address must be between 0 and 65535")
            self.mapper.add_mapping(mapping)
            self._refresh_mapping_tree()
            self._append_log(f"Saved mapping {mapping.device_id}:{mapping.address} -> {mapping.label}")
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Mapping Error", str(exc))

    def _refresh_mapping_tree(self) -> None:
        self.mapping_tree.delete(*self.mapping_tree.get_children())
        devices = set()
        for mapping in self.mapper.get_all_mappings().values():
            devices.add(mapping.device_id)
            self.mapping_tree.insert("", tk.END, values=(mapping.device_id, mapping.address, mapping.label, mapping.data_type.value, mapping.scale, mapping.offset, mapping.unit))
        values = sorted(devices) or ["device_1"]
        self.device_combo["values"] = values
        if self.device_var.get() not in values:
            self.device_var.set(values[0])

    def _refresh_statistics(self) -> None:
        self.stats_tree.delete(*self.stats_tree.get_children())
        for mapping in self.mapper.get_all_mappings().values():
            stats = self.mapper.get_statistics(mapping.device_id, mapping.address)
            if not stats:
                continue
            self.stats_tree.insert("", tk.END, values=(mapping.device_id, mapping.address, mapping.label, stats["min"], stats["max"], round(stats["avg"], 4), stats["count"], stats["latest"]))

    def _export_csv(self) -> None:
        if not self.records:
            messagebox.showwarning("Export", "There is no captured data to export")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not filename:
            return
        try:
            fieldnames = list(self.records[0].keys())
            with open(filename, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.records)
            self._append_log(f"Exported {len(self.records)} records to {filename}")
            messagebox.showinfo("Export", "CSV export completed")
        except OSError as exc:
            messagebox.showerror("Export Error", str(exc))

    def _export_json(self) -> None:
        if not self.records:
            messagebox.showwarning("Export", "There is no captured data to export")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(self.records, file, indent=2, ensure_ascii=False, default=str)
            self._append_log(f"Exported {len(self.records)} records to {filename}")
            messagebox.showinfo("Export", "JSON export completed")
        except OSError as exc:
            messagebox.showerror("Export Error", str(exc))

    def _clear_log(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear the visible log and captured export data?"):
            return
        self.records.clear()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _load_configuration(self) -> None:
        mappings_path = BASE_DIR / "config" / "mappings.json"
        try:
            with mappings_path.open("r", encoding="utf-8") as file:
                config = json.load(file)
            for item in config.get("mappings", []):
                self.mapper.add_mapping(
                    AddressMap(
                        device_id=str(item.get("device_id", "device_1")),
                        address=int(item["address"]),
                        label=str(item.get("label", f"Register {item['address']}")),
                        data_type=DataType(item.get("data_type", "uint16")),
                        scale=float(item.get("scale", 1.0)),
                        offset=float(item.get("offset", 0.0)),
                        unit=str(item.get("unit", "")),
                        description=str(item.get("description", "")),
                        min_value=item.get("min_value"),
                        max_value=item.get("max_value"),
                        alarm_threshold=item.get("alarm_threshold"),
                    )
                )
            self._refresh_mapping_tree()
        except FileNotFoundError:
            logger.warning("Mapping configuration not found: %s", mappings_path)
            self._refresh_mapping_tree()
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.error("Failed to load mappings: %s", exc)
            messagebox.showwarning("Configuration", f"Mappings could not be loaded: {exc}")
            self._refresh_mapping_tree()

    def _on_close(self) -> None:
        self.auto_scan_enabled = False
        if self.serial_handler:
            self.serial_handler.disconnect()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    SerialMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
