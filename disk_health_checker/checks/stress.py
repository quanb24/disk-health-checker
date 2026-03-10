from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Dict, Any

from ..models.config import StressConfig, GlobalConfig
from ..models.results import CheckResult, Severity

logger = logging.getLogger(__name__)


def _worker(path: str, stop_time: float, max_file_size: int, stats: Dict[str, Any]) -> None:
    rng = random.Random()
    thread_id = threading.get_ident()
    buf = bytearray(1024 * 1024)  # 1 MiB buffer

    while time.time() < stop_time:
        filename = os.path.join(path, f".dhc-stress-{thread_id}-{int(time.time() * 1000)}")
        size = rng.randint(1, max_file_size)
        written = 0
        try:
            t0 = time.time()
            with open(filename, "wb") as f:
                remaining = size
                while remaining > 0:
                    chunk = min(len(buf), remaining)
                    rng.random()  # mix RNG state lightly
                    f.write(buf[:chunk])
                    remaining -= chunk
                    written += chunk
            t1 = time.time()
            os.remove(filename)
            duration = t1 - t0
            with stats["lock"]:
                stats["bytes_written"] += written
                stats["ops"] += 1
                stats["durations"].append(duration)
        except Exception as exc:
            logger.warning("Stress worker error: %s", exc)
            with stats["lock"]:
                stats["errors"] += 1
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except OSError:
                pass


def run_stress_test(config: StressConfig, global_config: GlobalConfig) -> CheckResult:
    mount = config.mount_point

    if not os.path.isdir(mount):
        return CheckResult(
            check_name="StressTest",
            status=Severity.CRITICAL,
            summary=f"Stress target is not a directory: {mount}",
            details={},
            recommendations=[f"Provide a valid mount point or directory for stress testing."],
        )

    try:
        usage = os.statvfs(mount)
        free_bytes = usage.f_bavail * usage.f_frsize
    except OSError:
        free_bytes = None

    if free_bytes is not None:
        max_total = int(free_bytes * min(max(config.max_space_fraction, 0.01), 0.5))
    else:
        max_total = 50 * 1024 * 1024  # fallback: 50 MiB

    max_file_size = max_total // max(config.threads, 1)
    if max_file_size <= 0:
        return CheckResult(
            check_name="StressTest",
            status=Severity.WARNING,
            summary="Insufficient free space for stress test.",
            details={"free_bytes": free_bytes},
            recommendations=["Free up space on the filesystem before running a stress test."],
        )

    test_dir = os.path.join(mount, ".disk-health-checker-temp")
    os.makedirs(test_dir, exist_ok=True)

    stats: Dict[str, Any] = {
        "bytes_written": 0,
        "ops": 0,
        "errors": 0,
        "durations": [],
        "lock": threading.Lock(),
    }

    stop_time = time.time() + max(config.duration_seconds, 1)
    threads = []
    for _ in range(max(config.threads, 1)):
        t = threading.Thread(
            target=_worker,
            args=(test_dir, stop_time, max_file_size, stats),
            daemon=True,
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Try to clean up directory (ignore errors)
    try:
        if not os.listdir(test_dir):
            os.rmdir(test_dir)
    except OSError:
        pass

    durations = stats["durations"]
    total_bytes = stats["bytes_written"]
    total_ops = stats["ops"]
    errors = stats["errors"]

    elapsed = config.duration_seconds
    throughput_mb_s = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
    avg_latency = sum(durations) / len(durations) if durations else 0.0

    details: Dict[str, Any] = {
        "bytes_written": total_bytes,
        "ops": total_ops,
        "errors": errors,
        "throughput_mb_s": throughput_mb_s,
        "avg_op_duration_seconds": avg_latency,
        "threads": config.threads,
        "duration_seconds": config.duration_seconds,
        "max_file_size_bytes": max_file_size,
    }

    status = Severity.OK
    recommendations = []
    summary_parts = [f"Wrote {total_bytes} bytes in stress test ({throughput_mb_s:.2f} MiB/s)."]

    if errors > 0:
        status = Severity.CRITICAL
        summary_parts.append(f"{errors} I/O errors occurred.")
        recommendations.append("Investigate system logs for I/O errors and consider replacing the drive.")

    if total_ops == 0 and errors == 0:
        status = Severity.WARNING
        summary_parts.append("No operations were completed; verify write permissions and free space.")
        recommendations.append("Ensure the mount point is writable and not mounted read-only.")

    return CheckResult(
        check_name="StressTest",
        status=status,
        summary=" ".join(summary_parts),
        details=details,
        recommendations=recommendations,
    )


