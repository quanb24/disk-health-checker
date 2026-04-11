"""Read/write stress test.

Writes random data across multiple threads to exercise the drive under load.
Produces structured findings fed through the unified verdict pipeline.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any, Dict, List

from ..models.config import StressConfig, GlobalConfig
from ..models.results import CheckResult
from ..models.smart_types import Confidence, Finding, FindingSeverity
from .evaluate import findings_to_verdict, verdict_to_check_result

logger = logging.getLogger(__name__)


def _worker(
    path: str, stop_time: float, max_file_size: int, stats: Dict[str, Any],
) -> None:
    rng = random.Random()
    thread_id = threading.get_ident()
    buf = bytearray(1024 * 1024)  # 1 MiB buffer

    while time.time() < stop_time:
        filename = os.path.join(
            path, f".dhc-stress-{thread_id}-{int(time.time() * 1000)}"
        )
        size = rng.randint(1, max_file_size)
        written = 0
        try:
            t0 = time.time()
            with open(filename, "wb") as f:
                remaining = size
                while remaining > 0:
                    chunk = min(len(buf), remaining)
                    rng.random()
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
    findings: List[Finding] = []
    extra_details: Dict[str, Any] = {
        "mount_point": mount,
        "threads": config.threads,
        "duration_seconds": config.duration_seconds,
    }

    # ── Target existence ──
    if not os.path.isdir(mount):
        findings.append(Finding(
            code="stress.target_not_found",
            severity=FindingSeverity.FAIL,
            message=f"Stress target is not a directory: {mount}",
            evidence={"mount_point": mount},
        ))
        vr = findings_to_verdict(
            findings, confidence=Confidence.HIGH, check_category="stress test",
        )
        return verdict_to_check_result(
            "StressTest", vr,
            extra_details=extra_details,
            target_description=mount,
        )

    # ── Space calculation ──
    try:
        usage = os.statvfs(mount)
        free_bytes = usage.f_bavail * usage.f_frsize
    except OSError:
        free_bytes = None

    if free_bytes is not None:
        max_total = int(
            free_bytes * min(max(config.max_space_fraction, 0.01), 0.5)
        )
    else:
        max_total = 50 * 1024 * 1024  # fallback: 50 MiB

    max_file_size = max_total // max(config.threads, 1)
    if max_file_size <= 0:
        findings.append(Finding(
            code="stress.insufficient_space",
            severity=FindingSeverity.WARN,
            message="Insufficient free space for stress test.",
            evidence={"free_bytes": free_bytes},
        ))
        vr = findings_to_verdict(
            findings, confidence=Confidence.HIGH, check_category="stress test",
        )
        return verdict_to_check_result(
            "StressTest", vr,
            extra_details=extra_details,
            target_description=mount,
        )

    extra_details["max_file_size_bytes"] = max_file_size

    # ── Run stress workers ──
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

    try:
        if not os.listdir(test_dir):
            os.rmdir(test_dir)
    except OSError:
        pass

    # ── Collect results ──
    total_bytes = stats["bytes_written"]
    total_ops = stats["ops"]
    errors = stats["errors"]
    durations = stats["durations"]
    elapsed = config.duration_seconds
    throughput = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
    avg_latency = sum(durations) / len(durations) if durations else 0.0

    extra_details.update({
        "bytes_written": total_bytes,
        "ops": total_ops,
        "errors": errors,
        "throughput_mb_s": throughput,
        "avg_op_duration_seconds": avg_latency,
    })

    # ── Build findings ──
    if errors > 0:
        findings.append(Finding(
            code="stress.io_errors",
            severity=FindingSeverity.FAIL,
            message=f"{errors} I/O error(s) occurred during stress test.",
            evidence={"error_count": errors, "ops_completed": total_ops},
        ))

    if total_ops == 0 and errors == 0:
        findings.append(Finding(
            code="stress.no_ops_completed",
            severity=FindingSeverity.WARN,
            message="No operations completed. Check write permissions and free space.",
            evidence={"bytes_written": total_bytes},
        ))

    confidence = Confidence.HIGH

    vr = findings_to_verdict(
        findings, confidence=confidence, check_category="stress test",
    )
    return verdict_to_check_result(
        "StressTest", vr,
        extra_details=extra_details,
        target_description=mount,
    )
