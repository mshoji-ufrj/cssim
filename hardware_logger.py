from __future__ import annotations

import argparse
import csv
import json
import math
import os
import select
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import psutil


matplotlib.use("Agg")

import matplotlib.pyplot as plt


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "monitoring"
PID_FILE_NAME = "hardware_logger.pid"
SUMMARY_JSON_NAME = "summary.json"
REPORT_MD_NAME = "report.md"
SAMPLES_CSV_NAME = "samples.csv"
PLOT_PNG_NAME = "hardware_metrics.png"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_gb(value_bytes: float) -> float:
    return value_bytes / (1024 ** 3)


def format_mb(value_bytes: float) -> float:
    return value_bytes / (1024 ** 2)


def safe_round(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return round(value, digits)


def read_pid(pid_file: Path) -> int | None:
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
        return int(raw)
    except (FileNotFoundError, ValueError):
        return None


def process_is_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def ensure_not_running(pid_file: Path) -> None:
    pid = read_pid(pid_file)
    if process_is_running(pid):
        raise SystemExit(
            "A monitor is already running. "
            "Use the same terminal and type 'stop' to end it."
        )
    if pid_file.exists():
        pid_file.unlink()


@dataclass
class MetricSummary:
    label: str
    unit: str
    total: float = 0.0
    count: int = 0
    peak: float = float("-inf")
    peak_timestamp: str | None = None

    def add(self, value: float, timestamp: str) -> None:
        self.total += value
        self.count += 1
        if value > self.peak:
            self.peak = value
            self.peak_timestamp = timestamp

    @property
    def average(self) -> float | None:
        if self.count == 0:
            return None
        return self.total / self.count

    def to_dict(self) -> dict[str, Any]:
        peak = None if self.peak == float("-inf") else self.peak
        return {
            "label": self.label,
            "unit": self.unit,
            "average": safe_round(self.average),
            "peak": safe_round(peak),
            "peak_timestamp": self.peak_timestamp,
            "samples": self.count,
        }


class MonitorSession:
    def __init__(self, output_dir: Path, label: str, interval: float):
        self.output_dir = output_dir
        self.label = label
        self.interval = interval
        self.pid_file = self.output_dir / PID_FILE_NAME
        self.samples_file = self.output_dir / SAMPLES_CSV_NAME
        self.summary_file = self.output_dir / SUMMARY_JSON_NAME
        self.report_file = self.output_dir / REPORT_MD_NAME
        self.plot_file = self.output_dir / PLOT_PNG_NAME
        self.started_at = iso_now()
        self.stopped_at: str | None = None
        self.stop_requested = False
        self.stdin_commands_enabled = True
        self.sample_count = 0
        self.samples: list[dict[str, Any]] = []
        self.metrics: dict[str, MetricSummary] = {
            "cpu_percent": MetricSummary("CPU", "%"),
            "memory_percent": MetricSummary("RAM", "%"),
            "memory_used_gb": MetricSummary("RAM used", "GB"),
            "swap_percent": MetricSummary("Swap", "%"),
            "disk_read_mb_s": MetricSummary("Disk read", "MB/s"),
            "disk_write_mb_s": MetricSummary("Disk write", "MB/s"),
            "net_sent_mb_s": MetricSummary("Network sent", "MB/s"),
            "net_recv_mb_s": MetricSummary("Network received", "MB/s"),
        }
        self.has_temperature = False
        self.csv_header = [
            "timestamp",
            "cpu_percent",
            "memory_percent",
            "memory_used_gb",
            "swap_percent",
            "disk_read_mb_s",
            "disk_write_mb_s",
            "net_sent_mb_s",
            "net_recv_mb_s",
            "temperature_c",
        ]

    def request_stop(self, _signum: int, _frame: Any) -> None:
        self.stop_requested = True

    def run(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ensure_not_running(self.pid_file)
        self.pid_file.write_text(str(os.getpid()), encoding="utf-8")

        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        with self.samples_file.open("w", newline="", encoding="utf-8") as csv_handle:
            writer = csv.DictWriter(csv_handle, fieldnames=self.csv_header)
            writer.writeheader()

            prev_disk = psutil.disk_io_counters()
            prev_net = psutil.net_io_counters()
            prev_time = time.monotonic()

            psutil.cpu_percent(interval=None)

            while not self.stop_requested:
                if self._wait_interval():
                    break

                now = time.monotonic()
                elapsed = max(now - prev_time, 1e-9)
                prev_time = now

                current_disk = psutil.disk_io_counters()
                current_net = psutil.net_io_counters()
                memory = psutil.virtual_memory()
                swap = psutil.swap_memory()

                temperature = self._read_temperature()
                if temperature is not None:
                    self.has_temperature = True
                    if "temperature_c" not in self.metrics:
                        self.metrics["temperature_c"] = MetricSummary("Temperature", "°C")

                sample = {
                    "timestamp": iso_now(),
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "memory_percent": memory.percent,
                    "memory_used_gb": format_gb(memory.used),
                    "swap_percent": swap.percent,
                    "disk_read_mb_s": format_mb(current_disk.read_bytes - prev_disk.read_bytes) / elapsed,
                    "disk_write_mb_s": format_mb(current_disk.write_bytes - prev_disk.write_bytes) / elapsed,
                    "net_sent_mb_s": format_mb(current_net.bytes_sent - prev_net.bytes_sent) / elapsed,
                    "net_recv_mb_s": format_mb(current_net.bytes_recv - prev_net.bytes_recv) / elapsed,
                    "temperature_c": temperature,
                }

                prev_disk = current_disk
                prev_net = current_net

                writer.writerow({key: safe_round(value) if isinstance(value, float) else value for key, value in sample.items()})
                csv_handle.flush()
                self.samples.append(sample.copy())

                self.sample_count += 1
                for key, metric in self.metrics.items():
                    value = sample.get(key)
                    if isinstance(value, (int, float)):
                        metric.add(float(value), sample["timestamp"])

        self.stopped_at = iso_now()
        self._write_outputs()
        if self.pid_file.exists():
            self.pid_file.unlink()

    def _wait_interval(self) -> bool:
        end_time = time.monotonic() + self.interval
        while time.monotonic() < end_time:
            if self._read_terminal_command():
                return True
            if self.stop_requested:
                return True
            time.sleep(min(0.2, end_time - time.monotonic()))
        return self.stop_requested

    def _read_terminal_command(self) -> bool:
        if not self.stdin_commands_enabled:
            return self.stop_requested

        try:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
        except (OSError, ValueError):
            self.stdin_commands_enabled = False
            return self.stop_requested

        if not readable:
            return self.stop_requested

        command = sys.stdin.readline()
        if command == "":
            self.stdin_commands_enabled = False
            return self.stop_requested

        normalized = command.strip().lower()
        if normalized == "stop":
            print("'stop' command received. Ending monitoring...")
            self.stop_requested = True
            return True

        if normalized:
            print("Unknown command. Type 'stop' and press Enter to end monitoring.")

        return self.stop_requested

    def _read_temperature(self) -> float | None:
        try:
            sensors = psutil.sensors_temperatures()
        except (AttributeError, NotImplementedError):
            return None
        if not sensors:
            return None

        values: list[float] = []
        for entries in sensors.values():
            for entry in entries:
                if entry.current is not None:
                    values.append(float(entry.current))
        if not values:
            return None
        return sum(values) / len(values)

    def _write_outputs(self) -> None:
        payload = {
            "label": self.label,
            "interval_seconds": self.interval,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "sample_count": self.sample_count,
            "output_dir": str(self.output_dir),
            "metrics": {key: metric.to_dict() for key, metric in self.metrics.items()},
        }
        self.summary_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.report_file.write_text(self._build_markdown_report(payload), encoding="utf-8")
        self._save_plot()

    def _save_plot(self) -> None:
        if not self.samples:
            return

        ordered_metrics = [
            "cpu_percent",
            "memory_percent",
            "memory_used_gb",
            "temperature_c",
        ]
        available_metrics = [
            key
            for key in ordered_metrics
            if any(isinstance(sample.get(key), (int, float)) for sample in self.samples)
        ]
        if not available_metrics:
            return

        timestamps = [datetime.fromisoformat(str(sample["timestamp"])) for sample in self.samples]
        figure, axes = plt.subplots(
            len(available_metrics),
            1,
            figsize=(14, max(3 * len(available_metrics), 6)),
            sharex=True,
        )

        if len(available_metrics) == 1:
            axes = [axes]

        for axis, key in zip(axes, available_metrics):
            metric = self.metrics.get(key)
            if metric is None:
                continue

            values = [sample.get(key) for sample in self.samples]
            axis.plot(timestamps, values, linewidth=1.5, color="#1f77b4")
            axis.set_ylabel(metric.unit)
            axis.set_title(metric.label)
            axis.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)

        axes[-1].set_xlabel("Time")
        figure.suptitle(f"Hardware monitoring - {self.label}", y=0.995)
        figure.autofmt_xdate(rotation=30)
        figure.tight_layout(rect=(0, 0, 1, 0.965))
        figure.savefig(self.plot_file, dpi=150, bbox_inches="tight")
        plt.close(figure)

    def _build_markdown_report(self, payload: dict[str, Any]) -> str:
        lines = [
            f"# Hardware usage report - {self.label}",
            "",
            "## Session",
            f"- Start: {payload['started_at']}",
            f"- End: {payload['stopped_at']}",
            f"- Sampling interval: {payload['interval_seconds']} s",
            f"- Total samples: {payload['sample_count']}",
            f"- Raw data file: {self.samples_file.name}",
            f"- JSON summary: {self.summary_file.name}",
            f"- Plot: {self.plot_file.name}",
            "",
            "## Averages and peaks",
            "",
            "| Metric | Average | Peak | Peak time |",
            "|---|---:|---:|---|",
        ]

        ordered_metrics = [
            "cpu_percent",
            "memory_percent",
            "memory_used_gb",
            "swap_percent",
            "disk_read_mb_s",
            "disk_write_mb_s",
            "net_sent_mb_s",
            "net_recv_mb_s",
            "temperature_c",
        ]
        for key in ordered_metrics:
            metric = payload["metrics"].get(key)
            if not metric or metric["samples"] == 0:
                continue
            avg = metric["average"]
            peak = metric["peak"]
            unit = metric["unit"]
            lines.append(
                f"| {metric['label']} | {avg} {unit} | {peak} {unit} | {metric['peak_timestamp'] or '-'} |"
            )

        lines.extend(
            [
                "",
                "## How to interpret",
                "- Average values show the typical usage during the notebook session.",
                "- Peak values show the highest observed value for each metric during the session.",
                "- Disk and network rates are calculated in MB/s between consecutive samples.",
                "",
                "## Plot",
                f"![Monitoring plot]({self.plot_file.name})",
            ]
        )
        if not self.has_temperature:
            lines.append("- Temperature is not available on this system or requires additional permissions.")
        return "\n".join(lines) + "\n"


def run_monitor(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve()
    label = args.label or f"cssim_notebook_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session_dir = output_dir / label

    monitor = MonitorSession(output_dir=session_dir, label=label, interval=args.interval)
    print(f"Starting monitoring in: {session_dir}")
    print("Type 'stop' and press Enter in this terminal to end monitoring.")
    print("You can also stop it with Ctrl+C.")
    monitor.run()
    print(f"Report saved to: {monitor.report_file}")
    print(f"JSON summary saved to: {monitor.summary_file}")
    print(f"Plot saved to: {monitor.plot_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Monitors hardware usage with psutil and generates a report at the end."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Base directory where sessions will be saved.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Session name. If omitted, a timestamp-based name will be created.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Sampling interval in seconds.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run_monitor(args)


if __name__ == "__main__":
    raise SystemExit(main())