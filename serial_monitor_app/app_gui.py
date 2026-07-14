#!/usr/bin/env python3
"""
Main GUI Application
Tkinter-based interface for serial communication monitoring.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import logging
from datetime import datetime

from core.serial_handler import SerialPortHandler, SerialPortFinder
from core.modbus_protocol import ModbusRTU
from core.data_mapper import DataMapper, AddressMap, DataType
from core.storage import FileStorage, DatabaseStorage
from core.utils import format_hex, format_ascii, setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class SerialMonitorApp:
    """Main application window."""

    def __init__(self, root):
        self.root = root
        self.root.title("Serial Communication Monitor - Linux")
        self.root.geometry("1200x700")

        # Core components
        self.serial_handler = None
        self.modbus = None
        self.mapper = DataMapper()
        self.storage = FileStorage()
        self.db_storage = DatabaseStorage()
        self.running = False

        # Setup UI
        self._setup_ui()
        self._load_configuration()

    def _setup_ui(self):
        """Setup user interface."""
        # Top frame - Connection controls
        top_frame = ttk.LabelFrame(self.root, text="Connection Settings", padding=10)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Port:").pack(side=tk.LEFT, padx=5)
        self.port_var = tk.StringVar()
        port_combo = ttk.Combobox(top_frame, textvariable=self.port_var, width=15)
        port_combo.pack(side=tk.LEFT, padx=5)
        self._refresh_ports()

        ttk.Label(top_frame, text="Baudrate:").pack(side=tk.LEFT, padx=5)
        self.baudrate_var = tk.StringVar(value="9600")
        ttk.Combobox(
            top_frame,
            textvariable=self.baudrate_var,
            values=["300", "600", "1200", "2400", "4800", "9600", "19200", "38400", "115200"],
            width=10
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame, text="Refresh Ports", command=self._refresh_ports).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Connect", command=self._connect).pack(side=tk.LEFT, padx=5)
        self.disconnect_btn = ttk.Button(top_frame, text="Disconnect", command=self._disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(top_frame, text="Status: Disconnected", foreground="red")
        self.status_label.pack(side=tk.RIGHT, padx=5)

        # Notebook (tabs)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 1 - Monitor
        self.monitor_tab = ttk.Frame(notebook)
        notebook.add(self.monitor_tab, text="Real-Time Monitor")
        self._setup_monitor_tab()

        # Tab 2 - Address Mapping
        mapping_tab = ttk.Frame(notebook)
        notebook.add(mapping_tab, text="Address Mapping")
        self._setup_mapping_tab(mapping_tab)

        # Tab 3 - Data Log
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Data Log")
        self._setup_log_tab(log_tab)

        # Tab 4 - Statistics
        stats_tab = ttk.Frame(notebook)
        notebook.add(stats_tab, text="Statistics")
        self._setup_stats_tab(stats_tab)

    def _setup_monitor_tab(self):
        """Setup real-time monitor tab."""
        # Control frame
        ctrl_frame = ttk.Frame(self.monitor_tab)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(ctrl_frame, text="Device:").pack(side=tk.LEFT, padx=5)
        self.device_var = tk.StringVar()
        ttk.Combobox(ctrl_frame, textvariable=self.device_var, width=15).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Start Address:").pack(side=tk.LEFT, padx=5)
        self.start_addr_var = tk.StringVar(value="0")
        ttk.Entry(ctrl_frame, textvariable=self.start_addr_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="Quantity:").pack(side=tk.LEFT, padx=5)
        self.qty_var = tk.StringVar(value="10")
        ttk.Entry(ctrl_frame, textvariable=self.qty_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Button(ctrl_frame, text="Read", command=self._read_registers).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Auto Scan", command=self._toggle_auto_scan).pack(side=tk.LEFT, padx=5)

        # Data display
        tree_frame = ttk.Frame(self.monitor_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.data_tree = ttk.Treeview(
            tree_frame,
            columns=("Address", "Label", "Raw Value", "Scaled Value", "Unit", "Timestamp", "Alarm"),
            height=15,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.data_tree.yview)

        self.data_tree.column("#0", width=80, heading="ID")
        self.data_tree.column("Address", width=80, heading="Address")
        self.data_tree.column("Label", width=150, heading="Label")
        self.data_tree.column("Raw Value", width=100, heading="Raw Value")
        self.data_tree.column("Scaled Value", width=100, heading="Scaled Value")
        self.data_tree.column("Unit", width=80, heading="Unit")
        self.data_tree.column("Timestamp", width=150, heading="Timestamp")
        self.data_tree.column("Alarm", width=60, heading="Alarm")
        self.data_tree.pack(fill=tk.BOTH, expand=True)

    def _setup_mapping_tab(self, parent):
        """Setup address mapping configuration tab."""
        # Config frame
        config_frame = ttk.LabelFrame(parent, text="Add Mapping", padding=10)
        config_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(config_frame, text="Label:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        label_entry = ttk.Entry(config_frame, width=30)
        label_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Address:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        addr_entry = ttk.Entry(config_frame, width=30)
        addr_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Data Type:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        dtype_combo = ttk.Combobox(
            config_frame,
            values=[dt.value for dt in DataType],
            width=27
        )
        dtype_combo.grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Scale:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        scale_entry = ttk.Entry(config_frame, width=30)
        scale_entry.insert(0, "1.0")
        scale_entry.grid(row=3, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Unit:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        unit_entry = ttk.Entry(config_frame, width=30)
        unit_entry.grid(row=4, column=1, padx=5, pady=5)

        ttk.Button(config_frame, text="Save Mapping", width=20).grid(row=5, column=1, sticky=tk.E, padx=5, pady=10)

    def _setup_log_tab(self, parent):
        """Setup data logging tab."""
        # Control frame
        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(ctrl_frame, text="Export CSV", command=self._export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Export JSON", command=self._export_json).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT, padx=5)

        # Log display
        self.log_text = tk.Text(parent, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _setup_stats_tab(self, parent):
        """Setup statistics tab."""
        self.stats_tree = ttk.Treeview(
            parent,
            columns=("Label", "Min", "Max", "Avg", "Count", "Last"),
            height=20
        )
        self.stats_tree.column("#0", width=80, heading="Device")
        self.stats_tree.column("Label", width=150, heading="Label")
        self.stats_tree.column("Min", width=80, heading="Min")
        self.stats_tree.column("Max", width=80, heading="Max")
        self.stats_tree.column("Avg", width=80, heading="Average")
        self.stats_tree.column("Count", width=80, heading="Count")
        self.stats_tree.column("Last", width=100, heading="Last Value")
        self.stats_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _refresh_ports(self):
        """Refresh available serial ports."""
        finder = SerialPortFinder()
        ports = finder.list_ports()
        port_list = [p['port'] for p in ports]
        # Update combobox

    def _connect(self):
        """Connect to serial port."""
        port = self.port_var.get()
        baudrate = int(self.baudrate_var.get())

        if not port:
            messagebox.showerror("Error", "Please select a port")
            return

        try:
            self.serial_handler = SerialPortHandler(port, baudrate)
            if self.serial_handler.connect():
                self.modbus = ModbusRTU(self.serial_handler)
                self.status_label.config(text="Status: Connected", foreground="green")
                self.disconnect_btn.config(state=tk.NORMAL)
                self.running = True
                messagebox.showinfo("Success", f"Connected to {port}")
            else:
                messagebox.showerror("Error", f"Failed to connect to {port}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _disconnect(self):
        """Disconnect from serial port."""
        if self.serial_handler:
            self.serial_handler.disconnect()
            self.status_label.config(text="Status: Disconnected", foreground="red")
            self.disconnect_btn.config(state=tk.DISABLED)
            self.running = False
            messagebox.showinfo("Info", "Disconnected")

    def _read_registers(self):
        """Read holding registers."""
        if not self.modbus:
            messagebox.showerror("Error", "Not connected")
            return

        try:
            start_addr = int(self.start_addr_var.get())
            qty = int(self.qty_var.get())
            data = self.modbus.read_holding_registers(start_addr, qty)
            if data:
                self._display_data(data, start_addr)
        except ValueError:
            messagebox.showerror("Error", "Invalid address or quantity")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _display_data(self, data, start_address):
        """Display register data in tree."""
        self.data_tree.delete(*self.data_tree.get_children())
        for i, value in enumerate(data):
            address = start_address + i
            mapped = self.mapper.map_value("device_1", address, value)
            if mapped:
                self.data_tree.insert(
                    "",
                    tk.END,
                    text=str(i),
                    values=(
                        address,
                        mapped['label'],
                        mapped['raw_value'],
                        mapped['scaled_value'],
                        mapped['unit'],
                        mapped['timestamp'],
                        "YES" if mapped['in_alarm'] else "NO"
                    )
                )

    def _toggle_auto_scan(self):
        """Toggle automatic scanning."""
        pass

    def _export_csv(self):
        """Export data to CSV."""
        filename = filedialog.asksaveasfilename(defaultextension=".csv")
        if filename:
            messagebox.showinfo("Success", f"Exported to {filename}")

    def _export_json(self):
        """Export data to JSON."""
        filename = filedialog.asksaveasfilename(defaultextension=".json")
        if filename:
            messagebox.showinfo("Success", f"Exported to {filename}")

    def _clear_log(self):
        """Clear data log."""
        if messagebox.askyesno("Confirm", "Clear all logged data?"):
            self.log_text.delete(1.0, tk.END)

    def _load_configuration(self):
        """Load configuration from files."""
        config = self.storage.load_json("config/default_config.json")
        if config:
            logger.info("Configuration loaded")


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialMonitorApp(root)
    root.mainloop()
