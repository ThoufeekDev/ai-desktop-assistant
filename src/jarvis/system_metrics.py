"""Read basic system metrics from Linux procfs."""

from pathlib import Path

_PROC_STAT = Path("/proc/stat")
_PROC_MEMINFO = Path("/proc/meminfo")


def get_cpu_times() -> tuple[int, int]:
    """Return total CPU time and idle time."""
    with _PROC_STAT.open(encoding="utf-8") as file:
        for line in file:
            if line.startswith("cpu "):
                values = [int(value) for value in line.split()[1:]]

                if len(values) < 4:
                    raise RuntimeError("Incomplete CPU statistics")

                total = sum(values)
                idle = values[3]

                if len(values) > 4:
                    idle += values[4]

                return total, idle

    raise RuntimeError("CPU statistics are unavailable")


def get_cpu_usage(
    previous: tuple[int, int] | None,
) -> tuple[float | None, tuple[int, int]]:
    """Calculate CPU usage between two samples."""
    current = get_cpu_times()

    if previous is None:
        return None, current

    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]

    if total_delta <= 0:
        return None, current

    usage = 100.0 * (total_delta - idle_delta) / total_delta
    return max(0.0, min(100.0, usage)), current


def get_memory_usage() -> tuple[int, int, float]:
    """Return used memory, total memory in MiB, and usage percentage."""
    values: dict[str, int] = {}

    with _PROC_MEMINFO.open(encoding="utf-8") as file:
        for line in file:
            parts = line.split()

            if len(parts) >= 2 and parts[0] in {
                "MemTotal:",
                "MemAvailable:",
            }:
                values[parts[0]] = int(parts[1])

    if "MemTotal:" not in values or "MemAvailable:" not in values:
        raise RuntimeError("Memory statistics are unavailable")

    total_kib = values["MemTotal:"]
    available_kib = values["MemAvailable:"]

    if total_kib <= 0:
        raise RuntimeError("Invalid total memory")

    used_kib = max(0, total_kib - available_kib)
    percentage = used_kib / total_kib * 100.0

    return (
        round(used_kib / 1024),
        round(total_kib / 1024),
        percentage,
    )


def get_disk_usage(path: str = "/") -> tuple[int, int, int, float]:
    """Return used, total, and free disk space in GiB, plus usage percent."""
    import shutil

    usage = shutil.disk_usage(path)

    used_gib = usage.used / (1024**3)
    total_gib = usage.total / (1024**3)
    free_gib = usage.free / (1024**3)
    percentage = used_gib / total_gib * 100 if total_gib else 0.0

    return (
        round(used_gib),
        round(total_gib),
        round(free_gib),
        percentage,
    )



def get_system_info() -> dict[str, str]:
    """Return basic Linux system information."""
    import os
    import platform
    import socket

    info = {
        "hostname": socket.gethostname(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "logical_cpus": str(os.cpu_count() or "Unknown"),
    }

    try:
        with open("/etc/os-release", encoding="utf-8") as file:
            for line in file:
                if line.startswith("PRETTY_NAME="):
                    info["distribution"] = (
                        line.partition("=")[2]
                        .strip()
                        .strip('"')
                    )
                    break
    except OSError:
        info["distribution"] = "Unknown Linux distribution"

    try:
        with open("/proc/uptime", encoding="utf-8") as file:
            uptime_seconds = int(float(file.read().split()[0]))

        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60

        info["uptime"] = (
            f"{days}d {hours}h {minutes}m"
            if days
            else f"{hours}h {minutes}m"
        )
    except (OSError, ValueError, IndexError):
        info["uptime"] = "Unknown"

    return info


def get_swap_usage() -> tuple[int, int, float]:
    """Return used swap, total swap in MiB, and usage percentage."""
    values: dict[str, int] = {}

    with open("/proc/meminfo", encoding="utf-8") as file:
        for line in file:
            parts = line.split()

            if len(parts) >= 2 and parts[0] in {
                "SwapTotal:",
                "SwapFree:",
            }:
                values[parts[0]] = int(parts[1])

    total_kib = values.get("SwapTotal:", 0)
    free_kib = values.get("SwapFree:", 0)
    used_kib = max(0, total_kib - free_kib)

    percentage = (
        used_kib / total_kib * 100.0 if total_kib > 0 else 0.0
    )

    return (
        round(used_kib / 1024),
        round(total_kib / 1024),
        percentage,
    )


def get_mounted_storage() -> list[dict[str, str | int | float]]:
    """Return capacity information for mounted local filesystems."""
    import os
    import shutil

    filesystems = []

    with open("/proc/mounts", encoding="utf-8") as file:
        for line in file:
            parts = line.split()

            if len(parts) < 3:
                continue

            device, mountpoint, filesystem = parts[:3]

            if not device.startswith("/dev/"):
                continue

            if not os.path.isdir(mountpoint):
                continue

            try:
                usage = shutil.disk_usage(mountpoint)
            except OSError:
                continue

            total = usage.total
            if total == 0:
                continue

            filesystems.append(
                {
                    "device": device,
                    "mountpoint": mountpoint,
                    "filesystem": filesystem,
                    "total_gib": round(total / (1024**3), 1),
                    "used_gib": round(usage.used / (1024**3), 1),
                    "free_gib": round(usage.free / (1024**3), 1),
                    "percent": round(usage.used / total * 100, 1),
                }
            )

    return filesystems
