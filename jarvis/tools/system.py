"""System tools — files, bluetooth, wifi, battery, CPU, RAM, disk."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.system")

HOME = Path.home()


async def _run_cmd(cmd: str) -> str:
    """Run a shell command and return stdout."""
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode("utf-8", errors="replace").strip()


def build_system_tools() -> list[Tool]:
    """Return system monitoring tools."""

    async def _list_files(args: dict[str, Any]) -> str:
        """List files in a directory."""
        args = args or {}
        path = args.get("path", "~")
        path = os.path.expanduser(path)
        p = Path(path)
        if not p.exists():
            return f"Path not found: {path}"
        if not p.is_dir():
            return f"Not a directory: {path}"
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = []
            for entry in entries[:30]:
                if entry.is_dir():
                    lines.append(f"  [dir]  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    if size > 1_000_000:
                        size_str = f"{size / 1_000_000:.1f}MB"
                    elif size > 1_000:
                        size_str = f"{size / 1_000:.1f}KB"
                    else:
                        size_str = f"{size}B"
                    lines.append(f"  [file] {entry.name} ({size_str})")
            if not lines:
                return f"Directory is empty: {path}"
            return f"Contents of {path}:\n" + "\n".join(lines)
        except PermissionError:
            return f"Permission denied: {path}"
        except Exception as e:
            return f"Error listing files: {e}"

    async def _file_info(args: dict[str, Any]) -> str:
        """Get info about a specific file."""
        args = args or {}
        path = args.get("path", "")
        if not path:
            return "Error: path is required."
        path = os.path.expanduser(path)
        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        try:
            stat = p.stat()
            lines = [
                f"Name: {p.name}",
                f"Path: {p}",
                f"Type: {'directory' if p.is_dir() else 'file'}",
                f"Size: {stat.st_size:,} bytes",
                f"Modified: {stat.st_mtime}",
                f"Readable: {os.access(path, os.R_OK)}",
                f"Writable: {os.access(path, os.W_OK)}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def _find_files(args: dict[str, Any]) -> str:
        """Find files by name pattern."""
        args = args or {}
        pattern = args.get("pattern", "")
        directory = args.get("directory", "~")
        if not pattern:
            return "Error: pattern is required."
        directory = os.path.expanduser(directory)
        p = Path(directory)
        if not p.exists():
            return f"Directory not found: {directory}"
        try:
            matches = list(p.glob(f"**/{pattern}"))
            if not matches:
                return f"No files matching '{pattern}' in {directory}"
            lines = []
            for m in matches[:20]:
                size = m.stat().st_size if m.is_file() else 0
                lines.append(f"  {m} ({size:,} bytes)" if m.is_file() else f"  {m}/")
            return f"Found {len(matches)} matches:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def _battery(args: dict[str, Any]) -> str:
        """Get battery status."""
        args = args or {}
        try:
            # Try /sys/class/power_supply first
            bat_path = Path("/sys/class/power_supply")
            batteries = [p for p in bat_path.iterdir() if p.name.startswith("BAT")]
            if batteries:
                bat = batteries[0]
                capacity = (bat / "capacity").read_text().strip()
                status = (bat / "status").read_text().strip()
                try:
                    voltage = (bat / "voltage_now").read_text().strip()
                    voltage_v = f"{int(voltage) / 1_000_000:.2f}V"
                except Exception:
                    voltage_v = "unknown"
                return f"Battery: {capacity}% ({status}) — {voltage_v}"

            # Try upower
            result = await _run_cmd("upower -i /org/freedesktop/UPower/devices/battery_BAT0 2>/dev/null")
            if result:
                lines = []
                for line in result.split("\n"):
                    line = line.strip()
                    if "percentage" in line or "state" in line or "time" in line or "capacity" in line:
                        lines.append(line)
                return "\n".join(lines) if lines else "Battery info unavailable"

            return "No battery found."
        except Exception as e:
            return f"Battery error: {e}"

    async def _wifi_status(args: dict[str, Any]) -> str:
        """Get WiFi connection status."""
        args = args or {}
        try:
            result = await _run_cmd(
                "nmcli -t -f NAME,TYPE,DEVICE,STATE con show --active 2>/dev/null"
            )
            if not result:
                return "Could not read WiFi status."

            wifi_lines = []
            for line in result.split("\n"):
                parts = line.split(":")
                if len(parts) >= 4 and "wireless" in parts[1]:
                    wifi_lines.append(f"Connected to: {parts[0]} (device: {parts[2]}, state: {parts[3]})")

            if not wifi_lines:
                return "No active WiFi connection."

            # Get signal strength
            signal = await _run_cmd("nmcli -t -f IN-USE,SIGNAL dev wifi 2>/dev/null | grep '^*:' | cut -d: -f2")
            wifi_lines.append(f"Signal: {signal}%" if signal else "Signal: unknown")

            return "\n".join(wifi_lines)
        except Exception as e:
            return f"WiFi error: {e}"

    async def _bluetooth_status(args: dict[str, Any]) -> str:
        """Get Bluetooth status."""
        args = args or {}
        try:
            result = await _run_cmd("bluetoothctl show 2>/dev/null")
            if not result:
                return "Bluetoothctl not available."

            lines = []
            for line in result.split("\n"):
                line = line.strip()
                if any(k in line.lower() for k in ["powered", "name", "alias", "discoverable"]):
                    lines.append(line)

            # List paired devices
            devices = await _run_cmd("bluetoothctl devices Paired 2>/dev/null")
            if devices:
                lines.append("\nPaired devices:")
                for line in devices.split("\n"):
                    if line.strip():
                        parts = line.split(" ", 2)
                        if len(parts) >= 3:
                            lines.append(f"  {parts[2]} ({parts[1]})")

            return "\n".join(lines) if lines else "Bluetooth info unavailable."
        except Exception as e:
            return f"Bluetooth error: {e}"

    async def _system_info(args: dict[str, Any]) -> str:
        """Get CPU, RAM, and disk usage."""
        args = args or {}
        try:
            import psutil

            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            freq_str = f" @ {cpu_freq.current:.0f}MHz" if cpu_freq else ""

            # RAM
            mem = psutil.virtual_memory()
            ram_used = f"{mem.used / (1024**3):.1f}GB"
            ram_total = f"{mem.total / (1024**3):.1f}GB"

            # Disk
            disk = psutil.disk_usage("/")
            disk_used = f"{disk.used / (1024**3):.1f}GB"
            disk_total = f"{disk.total / (1024**3):.1f}GB"
            disk_pct = f"{disk.percent}%"

            # Load average
            load = os.getloadavg()

            lines = [
                f"CPU: {cpu_percent}% ({cpu_count} cores{freq_str})",
                f"Load avg: {load[0]:.1f} {load[1]:.1f} {load[2]:.1f}",
                f"RAM: {ram_used} / {ram_total} ({mem.percent}%)",
                f"Disk: {disk_used} / {disk_total} ({disk_pct})",
            ]

            # Temperature if available
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        if entries:
                            lines.append(f"Temp ({name}): {entries[0].current}°C")
            except Exception:
                pass

            return "\n".join(lines)
        except ImportError:
            return "psutil not installed. Run: pip install psutil"
        except Exception as e:
            return f"System info error: {e}"

    return [
        Tool(
            name="list_files",
            description="List files and folders in a directory on the computer.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: home directory)",
                    },
                },
                "required": [],
            },
            handler=_list_files,
            requires_confirm=False,
        ),
        Tool(
            name="file_info",
            description="Get detailed info about a specific file or folder (size, permissions, modification date).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Full path to the file or folder",
                    },
                },
                "required": ["path"],
            },
            handler=_file_info,
            requires_confirm=False,
        ),
        Tool(
            name="find_files",
            description="Search for files by name pattern on the computer.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Filename pattern (e.g. '*.pdf', 'report*')",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in (default: home)",
                    },
                },
                "required": ["pattern"],
            },
            handler=_find_files,
            requires_confirm=False,
        ),
        Tool(
            name="battery_status",
            description="Check laptop battery level and charging status.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_battery,
            requires_confirm=False,
        ),
        Tool(
            name="wifi_status",
            description="Check WiFi connection status and signal strength.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_wifi_status,
            requires_confirm=False,
        ),
        Tool(
            name="bluetooth_status",
            description="Check Bluetooth status and paired devices.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_bluetooth_status,
            requires_confirm=False,
        ),
        Tool(
            name="system_info",
            description="Get CPU usage, RAM, disk space, and system load. Use this when the user asks about system performance or resources.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_system_info,
            requires_confirm=False,
        ),
    ]
